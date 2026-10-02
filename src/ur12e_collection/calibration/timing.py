"""Operator-approved calibration motion and stationary capture timing."""

import dataclasses

from ur12e_collection.control.model import Limits

DWELL_NS = 1_500_000_000
MOVE_SPEED = 0.15
MOVE_ACCELERATION = 0.30
STOP_DECELERATION = 0.30


def motion_limits(limits: Limits) -> Limits:
    """Use calibration rates without changing shared station configuration."""
    return dataclasses.replace(
        limits,
        ready_speed=MOVE_SPEED,
        ready_acceleration=MOVE_ACCELERATION,
        speed=max(limits.speed, MOVE_SPEED),
        acceleration=max(limits.acceleration, MOVE_ACCELERATION),
    )
