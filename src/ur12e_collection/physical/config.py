"""Commissioning policy, separate from simulated motion settings."""

import ipaddress
import math
import pathlib

from ur12e_collection.control import guards


def validate(value):
    """Require explicit physical identity, reviewed bounds and tool policy."""
    follower = value["follower"]
    ipaddress.IPv4Address(follower["host"])
    if not follower.get("serial") or not follower.get("interface"):
        raise ValueError("physical serial and Ethernet interface are required")
    if value.get("twins"):
        raise ValueError("commissioning requires an isolated physical primary")
    if value.get("home_open_gripper") is not False:
        raise ValueError("physical HOME must not release the gripper")
    limits = value["limits"]
    ceilings = {
        "speed": math.radians(12),
        "acceleration": math.radians(15),
        "ready_speed": math.radians(3),
        "ready_acceleration": math.radians(6),
        "freshness_ns": 250_000_000,
        "arrival": math.radians(0.1),
        "stopped_speed": math.radians(0.01),
    }
    if any(getattr(limits, key) > maximum for key, maximum in ceilings.items()):
        raise ValueError("physical limits exceed the commissioning envelope")
    home = tuple(map(math.radians, (0, -90, -90, -90, 90, 0)))
    if limits.ready != home:
        raise ValueError("physical HOME differs from the aligned pose")
    stop = follower["stop_deceleration"]
    if (
        not isinstance(stop, (int, float))
        or isinstance(stop, bool)
        or stop != math.radians(2)
    ):
        raise ValueError("commissioning stop requires 2 degrees/s squared")
    servo_stop = follower.get("servo_stop_deceleration_m_s2")
    if servo_stop is not None and servo_stop != 0.1:
        raise ValueError(
            "servo stop must use the separately reviewed tool units"
        )
    value["guards"] = guards.Policy(**value["guards"])
    tool = value["gripper"]
    for key in ("speed", "force", "open_tolerance"):
        if (
            not isinstance(tool[key], int)
            or isinstance(tool[key], bool)
            or not 0 <= tool[key] <= 255
        ):
            raise ValueError(f"invalid raw Hand-E {key}")
    if tool["speed"] != 32 or tool["force"] != 32 or tool["open_tolerance"] > 5:
        raise ValueError("commissioning Hand-E profile differs from alignment")
    if tool["port"] != 63352:
        raise ValueError("explicit installed URCap endpoint 63352 required")
    value["evidence"] = pathlib.Path(value["evidence"]).expanduser()
