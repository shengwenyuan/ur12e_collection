"""Strict camera-specific replay targets, never substituted for measurements."""

import dataclasses
import json
import math
import pathlib

from ur12e_collection.calibration import aprilgrid, board, manifest, traversal
from ur12e_collection.control import model

JOINT_NAMES = ["base", "shoulder", "elbow", "wrist1", "wrist2", "wrist3"]
DETECTION = board.DetectionLimits(20.0, 0.01, 1.0, 0.05, 16)


@dataclasses.dataclass(frozen=True)
class Route:
    """Validated identity, pixel profile and immutable joint route."""

    document: dict
    poses: tuple
    start: tuple

    @property
    def role(self):
        """Camera identity follows production role names."""
        return self.document["role"]

    @property
    def profile(self):
        """RGB mode is independent of the production RGB-D pipeline."""
        return self.document["profile"]


def parse(value: dict, role: str, limits: model.Limits) -> Route:
    """Preflight the whole file without devices, IK or angle wrapping."""
    manifest.keys(
        value,
        (
            "schema_version",
            "role",
            "camera_serial",
            "camera_model",
            "base_id",
            "mount_id",
            "robot_serial",
            "board_mount_id",
            "board_attachment",
            "joint_names",
            "units",
            "start_q",
            "profile",
            "board",
            "waypoints",
        ),
    )
    _identity(value, role)
    start = tuple(value["start_q"])
    limits.check(start)
    entries = value["waypoints"]
    if not isinstance(entries, list) or not 20 <= len(entries) <= 40:
        raise ValueError("20..40 capture waypoints required")
    poses = []
    for item in entries:
        manifest.keys(item, ("pose_id", "q", "split"), ("via",))
        manifest.identity(item["pose_id"])
        points = tuple(tuple(q) for q in item.get("via", [])) + (
            tuple(item["q"]),
        )
        if len(points) > 20:
            raise ValueError("too many transit points")
        for point in points:
            limits.check(point)
        poses.append(
            traversal.Pose(item["pose_id"], points, (role,), item["split"])
        )
    if len({p.pose_id for p in poses}) != len(poses):
        raise ValueError("duplicate capture pose IDs")
    if len({p.waypoints[-1] for p in poses}) != len(poses):
        raise ValueError("duplicate capture joint targets")
    if (
        sum(p.split == "training" for p in poses) < 15
        or sum(p.split == "validation" for p in poses) < 5
    ):
        raise ValueError("at least 15 training and 5 held-out poses required")
    return Route(value, tuple(poses), start)


def load(path: pathlib.Path, role: str, limits: model.Limits) -> Route:
    """Load only explicit, finite JSON data; no robot access."""
    try:
        return parse(json.loads(path.read_text(encoding="utf-8")), role, limits)
    except (KeyError, TypeError) as error:
        raise ValueError(f"invalid calibration route: {error}") from error


def solver_limits() -> dict:
    """Initial numerical gates; never automatically relaxed to get a result."""
    return {
        "translation_m": 0.002,
        "rotation_rad": math.radians(1),
        "reprojection_px": 1.0,
    }


def _identity(value, role):
    """Bind joint, board, camera and pixel-profile conventions."""
    if value["schema_version"] != 1 or role not in (
        "third_left",
        "third_right",
        "wrist",
    ):
        raise ValueError("unsupported calibration route or role")
    if value["role"] != role or value["joint_names"] != JOINT_NAMES:
        raise ValueError("route role or joint order differs")
    if value["units"] != "rad":
        raise ValueError("route joint angles must explicitly use rad")
    for key in (
        "camera_serial",
        "base_id",
        "mount_id",
        "robot_serial",
        "board_mount_id",
    ):
        manifest.identity(value[key])
    models = ("D405",) if role == "wrist" else ("D435IF", "D435i")
    if value["camera_model"] not in models:
        raise ValueError("camera model differs from the selected role")
    attachment = "base" if role == "wrist" else "flange"
    if value["board_attachment"] != attachment:
        raise ValueError(
            "board attachment cannot move with the selected camera"
        )
    aprilgrid.Grid(**value["board"])
    manifest.keys(value["profile"], ("width", "height", "fps", "format"))
    profile = value["profile"]
    allowed = ((640, 480), (1280, 720))
    if role != "wrist":
        allowed += ((1920, 1080),)
    if (
        any(
            (not isinstance(profile[k], int) or isinstance(profile[k], bool))
            for k in ("width", "height", "fps")
        )
        or (profile["width"], profile["height"]) not in allowed
        or profile["fps"] != 30
        or profile["format"] != "rgb8"
    ):
        raise ValueError("unsupported explicit RGB8/30 calibration profile")
