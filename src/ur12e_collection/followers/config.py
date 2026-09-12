"""Explicit native follower configuration; all paths are file-relative."""

import json
import math
import pathlib

from ur12e_collection.control import model
from ur12e_collection.followers import physics
from ur12e_collection.physical import config as physical_config

BACKENDS = ("isaac_kinematic", "isaac_physics")


def resolve(base: pathlib.Path, value: str) -> pathlib.Path:
    """Resolve a configured location without assuming sibling repositories."""
    return (base / pathlib.Path(value).expanduser()).resolve()


def load(path: pathlib.Path) -> dict:
    """Validate before opening leader devices or importing a follower SDK."""
    path = path.expanduser().resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("recording") is not False:
        raise ValueError("native teleop requires schema 1 and recording=false")
    if value["follower"]["backend"] not in (*BACKENDS, "ur"):
        raise model.ControlError("unsupported follower backend")
    if (
        value["follower"]["backend"] == "ur"
        and value.get("physical_profile") != "commissioning-v1"
    ):
        raise model.ControlError(
            "explicit physical commissioning profile required"
        )
    limits = dict(value["limits"])
    for key in ("lower", "upper", "ready"):
        limits[key] = tuple(limits[key])
    value["limits"] = model.Limits(**limits)
    gripper = value["gripper"]
    sign = gripper["closing_sign"]
    speed = gripper.get("aperture_speed_m_s", 0.05)
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
    if value["follower"]["backend"] == "ur":
        value["evidence"] = resolve(path.parent, value["evidence"])
        physical_config.validate(value)
        return value
    endpoints = set()
    for follower in [value["follower"], *value.get("twins", [])]:
        if follower["backend"] not in BACKENDS:
            raise model.ControlError("only native Isaac endpoints are enabled")
        follower["endpoint"] = resolve(path.parent, follower["endpoint"])
        if follower["endpoint"] in endpoints:
            raise ValueError("primary and twin endpoints must be distinct")
        endpoints.add(follower["endpoint"])
    scene_paths(value["scene"], path.parent)
    if value["follower"]["backend"] == "isaac_physics":
        value["physics"] = physics.Settings(**value["physics"])
    return value


def scene_paths(scene, base):
    """Validate portable scene entrypoints independently of device settings."""
    scene["root"] = resolve(base, scene["root"])
    for key in ("entrypoint", "adapter"):
        location = (scene["root"] / scene[key]).resolve()
        if not location.is_relative_to(scene["root"]) or not location.is_file():
            raise ValueError(
                f"scene {key} must exist inside its configured root"
            )
        scene[key] = location
    if not 1 <= scene["display_hz"] <= 60:
        raise ValueError("display_hz must be in [1, 60]")
