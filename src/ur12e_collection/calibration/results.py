"""Offline solve, immutable evidence bundles and explicit station activation."""

import hashlib
import json
import pathlib
import shutil

import cv2

from ur12e_collection import filesystem, station
from ur12e_collection.calibration import board, geometry, manifest


def _file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _image(root, name):
    path = pathlib.Path(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.suffix.lower() != ".png"
    ):
        raise ValueError("calibration image must be a relative lossless PNG")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("calibration image is outside its evidence directory")
    return resolved


def evaluate(document: dict, root: pathlib.Path) -> dict:
    """Detect real images or solve explicitly labeled synthetic observations."""
    manifest.keys(
        document, ("schema_version", "observations", *manifest.CONTEXT)
    )
    if document["schema_version"] != 1:
        raise ValueError("unsupported calibration input version")
    context = {key: document[key] for key in manifest.CONTEXT}
    manifest.context(context)
    splits = {"training": [], "validation": []}
    detections, evidence = {}, {"input.json": manifest.digest(document)}
    for item in document["observations"]:
        common = ("pose_id", "split", "T_base_flange")
        if "image" in item:
            manifest.keys(item, (*common, "image"))
            path = _image(root, item["image"])
            evidence[item["image"]] = _file_digest(path)
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("calibration PNG cannot be decoded")
            detection = board.detect(
                cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
                board.Board(**context["board"]),
                context["intrinsics"],
                board.DetectionLimits(**context["detection_limits"]),
            )
        else:
            manifest.keys(item, (*common, "T_camera_board", "reprojection_px"))
            if not context["simulated"]:
                raise ValueError("physical calibration requires image evidence")
            detection = {
                key: item[key] for key in ("T_camera_board", "reprojection_px")
            }
        if item["split"] not in splits:
            raise ValueError("checkpoint must be training or validation")
        observation = geometry.Observation(
            item["pose_id"],
            item["T_base_flange"],
            detection["T_camera_board"],
            detection["reprojection_px"],
        )
        splits[item["split"]].append(observation)
        detections[item["pose_id"]] = detection
    solution = geometry.solve(
        "wrist" if context["role"] == "wrist" else "fixed",
        splits["training"],
        splits["validation"],
        geometry.Thresholds(**context["thresholds"]),
    )
    value = {
        "schema_version": 1,
        "context": context,
        "solution": solution,
        "evidence": evidence,
        "detections": detections,
    }
    value["calibration_id"] = manifest.digest(value)
    manifest.result(value)
    return value


def solve(input_path: pathlib.Path, destination: pathlib.Path) -> dict:
    """Publish rechecked evidence; keep failed bundles partial."""
    if destination.name.endswith((".partial", ".lock")):
        raise ValueError("reserved calibration bundle suffix")
    document = json.loads(input_path.read_text(encoding="utf-8"))
    # Fail invalid geometry before reserving any successful result path.
    expected = evaluate(document, input_path.parent)
    partial = destination.with_name(destination.name + ".partial")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    partial.mkdir()
    (partial / "input.json").write_text(
        json.dumps(document, indent=2), encoding="utf-8"
    )
    for name in expected["evidence"]:
        if name == "input.json":
            continue
        target = partial / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_image(input_path.parent, name), target)
    observed = evaluate(document, partial)
    if observed != expected:
        raise ValueError("calibration evidence changed during copy")
    (partial / "result.json").write_text(
        json.dumps(observed, indent=2), encoding="utf-8"
    )
    filesystem.publish(partial, destination)
    return observed


def verify(bundle: pathlib.Path) -> dict:
    """Re-detect and re-solve copied evidence before trusting its result."""
    if bundle.name.endswith(".partial"):
        raise ValueError("partial calibration cannot be activated")
    value = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    manifest.result(value)
    document = json.loads((bundle / "input.json").read_text(encoding="utf-8"))
    if evaluate(document, bundle) != value:
        raise ValueError("calibration evidence or solution differs")
    return value


def activate(bundle: pathlib.Path, station_path: pathlib.Path) -> dict:
    """Copy a verified camera result only into its matching declared setup."""
    value = verify(bundle)

    def change(config):
        selected = config["calibration"] or {"schema_version": 1, "cameras": {}}
        selected["cameras"][value["context"]["role"]] = value
        config["calibration"] = selected
        return config

    return station.update(station_path, change)


def declare(station_path: pathlib.Path, setup: dict) -> dict:
    """Invalidate affected results when the operator declares a new setup."""
    manifest.setup(setup)

    def change(config):
        kept = {}
        for role, value in (
            (config["calibration"] or {}).get("cameras", {}).items()
        ):
            source = value["context"]
            if (
                source["base_id"] == setup["base_id"]
                and source["mount_id"] == setup["mounts"][role]
                and source["simulated"] == setup["simulated"]
            ):
                kept[role] = value
        config["setup"] = setup
        config["calibration"] = (
            {"schema_version": 1, "cameras": kept} if kept else None
        )
        return config

    return station.update(station_path, change)
