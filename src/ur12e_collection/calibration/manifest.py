"""Strict offline calibration context and self-contained active results."""

import hashlib
import json

from ur12e_collection import contracts
from ur12e_collection.calibration import board, geometry

CONTEXT = (
    "simulated",
    "role",
    "camera_serial",
    "base_id",
    "mount_id",
    "script_revision",
    "board",
    "intrinsics",
    "thresholds",
    "detection_limits",
)


def keys(value: dict, required, optional=()) -> None:
    """Reject unknown and missing fields before interpretation."""
    if (
        not isinstance(value, dict)
        or set(required) - value.keys()
        or (value.keys() - set(required) - set(optional))
    ):
        raise ValueError("invalid calibration fields")
    json.dumps(value, allow_nan=False)


def identity(value) -> None:
    """Require an explicit nonempty identity."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("calibration identity is missing")


def digest(value: dict) -> str:
    """Identify canonical JSON content independently of its file location."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def context(value: dict) -> None:
    """Validate measured board scale, optics and declared source identities."""
    keys(value, CONTEXT)
    if not isinstance(value["simulated"], bool):
        raise ValueError("explicit calibration simulation flag required")
    if value["role"] not in contracts.CAMERA_ROLES:
        raise ValueError("invalid calibration camera role")
    for name in ("camera_serial", "base_id", "mount_id", "script_revision"):
        identity(value[name])
    board.Board(**value["board"]).create()
    board.optics(value["intrinsics"])
    if (
        value["intrinsics"].get("width"),
        value["intrinsics"].get("height"),
    ) != (640, 480):
        raise ValueError("calibration requires the 640x480 color profile")
    geometry.Thresholds(**value["thresholds"])
    board.DetectionLimits(**value["detection_limits"])


def setup(value: dict) -> None:
    """Declared base/mount generations cannot establish physical immobility."""
    keys(value, ("base_id", "mounts", "simulated"))
    identity(value["base_id"])
    if not isinstance(value["simulated"], bool):
        raise ValueError("explicit setup simulation flag required")
    keys(value["mounts"], contracts.CAMERA_ROLES)
    for mount in value["mounts"].values():
        identity(mount)


def result(value: dict) -> None:
    """Verify identity, transform direction and accepted residuals."""
    keys(
        value,
        (
            "schema_version",
            "calibration_id",
            "context",
            "solution",
            "evidence",
            "detections",
        ),
    )
    if value["schema_version"] != 1 or value["calibration_id"] != digest(
        {k: v for k, v in value.items() if k != "calibration_id"}
    ):
        raise ValueError("calibration result hash/version differs")
    context(value["context"])
    solution = value["solution"]
    wrist = value["context"]["role"] == "wrist"
    if solution["round"] != ("wrist" if wrist else "fixed"):
        raise ValueError("calibration transform direction differs from role")
    geometry.transform(
        solution["T_flange_camera" if wrist else "T_base_camera"]
    )
    geometry.transform(solution["T_base_board" if wrist else "T_flange_board"])
    limits = geometry.Thresholds(**solution["thresholds"])
    for residual in solution["residuals"]:
        for name in ("translation_m", "rotation_rad", "reprojection_px"):
            if not 0 <= residual[name] <= getattr(limits, name):
                raise ValueError("active calibration exceeds its thresholds")


def active(config: dict) -> None:
    """Validate copied results without external files or device access."""
    declared = config.get("setup")
    if declared is not None:
        setup(declared)
    selected = config["calibration"]
    if selected is None:
        return
    if declared is None:
        raise ValueError("active calibration requires a declared setup")
    keys(selected, ("schema_version", "cameras"))
    if selected["schema_version"] != 1 or not selected["cameras"]:
        raise ValueError("active calibration must name at least one camera")
    keys(selected["cameras"], (), contracts.CAMERA_ROLES)
    for role, value in selected["cameras"].items():
        result(value)
        source = value["context"]
        if (
            source["role"] != role
            or source["camera_serial"] != config["cameras"][role]["serial"]
            or source["base_id"] != declared["base_id"]
            or source["mount_id"] != declared["mounts"][role]
            or source["simulated"] != declared["simulated"]
        ):
            raise ValueError("calibration differs from camera/setup identity")
