"""Explicit native follower configuration; all paths are file-relative."""

import json
import math
import pathlib

from ur12e_collection.control import model


def resolve(base: pathlib.Path, value: str) -> pathlib.Path:
    """Resolve a configured location without assuming sibling repositories."""
    return (base / pathlib.Path(value).expanduser()).resolve()


def load(path: pathlib.Path) -> dict:
    """Validate before opening leader devices or importing a follower SDK."""
    path = path.expanduser().resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("recording") is not False:
        raise ValueError("native teleop requires schema 1 and recording=false")
    if value["follower"]["backend"] != "isaac_kinematic":
        raise model.ControlError("physical follower control is disabled")
    limits = dict(value["limits"])
    for key in ("lower", "upper", "ready"):
        limits[key] = tuple(limits[key])
    value["limits"] = model.Limits(**limits)
    gripper = value["gripper"]
    sign = gripper["closing_sign"]
    speed = gripper["aperture_speed_m_s"]
    if isinstance(sign, bool) or sign not in (-1, 1):
        raise ValueError("gripper closing_sign must be -1 or 1")
    if (
        isinstance(speed, bool)
        or not isinstance(speed, (int, float))
        or not math.isfinite(speed)
        or speed <= 0
    ):
        raise ValueError("gripper aperture speed must be positive and finite")
    value["leader"]["calibration"] = resolve(
        path.parent, value["leader"]["calibration"]
    )
    if value["leader"]["manual_support"] is not True:
        raise ValueError("leader manual support must be explicit")
    endpoints = set()
    for follower in [value["follower"], *value.get("twins", [])]:
        if follower["backend"] != "isaac_kinematic":
            raise model.ControlError("only native Isaac endpoints are enabled")
        follower["endpoint"] = resolve(path.parent, follower["endpoint"])
        if follower["endpoint"] in endpoints:
            raise ValueError("primary and twin endpoints must be distinct")
        endpoints.add(follower["endpoint"])
    scene = value["scene"]
    scene["root"] = resolve(path.parent, scene["root"])
    for key in ("entrypoint", "adapter"):
        location = (scene["root"] / scene[key]).resolve()
        if not location.is_relative_to(scene["root"]) or not location.is_file():
            raise ValueError(
                f"scene {key} must exist inside its configured root"
            )
        scene[key] = location
    if not 1 <= scene["display_hz"] <= 60:
        raise ValueError("display_hz must be in [1, 60]")
    return value
