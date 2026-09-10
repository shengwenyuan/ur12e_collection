"""Immutable, unwrapped joint-space control inputs and explicit limits."""

import dataclasses
import math

# Exact scalar types intentionally reject bool as a number.
# pylint: disable=unidiomatic-typecheck
from typing import Protocol

Joints = tuple[float, ...]


class ControlError(RuntimeError):
    """Control cannot continue without a new, explicitly initialized owner."""


def joints(value: Joints) -> None:
    """Reject malformed vectors without normalizing their angle branches."""
    if not isinstance(value, tuple) or len(value) != 6:
        raise ControlError("six immutable joint values required")
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in value):
        raise ControlError("joint values must be finite numbers")


def distance(left: Joints, right: Joints) -> float:
    """Return the largest joint difference, without angle wrapping."""
    return max(abs(a - b) for a, b in zip(left, right))


@dataclasses.dataclass(frozen=True)
class Limits:
    """Application bounds; these do not replace controller safety settings."""

    # One immutable set of independent joint, rate and timing limits.
    # pylint: disable=too-many-instance-attributes

    lower: Joints
    upper: Joints
    ready: Joints
    ready_speed: float = 0.3
    ready_acceleration: float = 0.5
    speed: float = 1.0
    acceleration: float = 3.0
    step: float = 0.08
    freshness_ns: int = 250_000_000
    arrival: float = 0.01
    stopped_speed: float = 0.01

    def __post_init__(self):
        joints(self.lower)
        joints(self.upper)
        if any(a >= b for a, b in zip(self.lower, self.upper)):
            raise ControlError("joint bounds must be ordered")
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if field.name not in ("lower", "upper", "ready") and (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ControlError("control limits must be finite and positive")
        if (
            self.ready_speed > self.speed
            or self.ready_acceleration > self.acceleration
        ):
            raise ControlError("READY limits exceed general limits")
        if type(self.freshness_ns) is not int:
            raise ControlError("freshness must be integer nanoseconds")
        self.check(self.ready)

    def check(self, q: Joints) -> None:
        """Reject any joint outside the configured inclusive bounds."""
        joints(q)
        if any(
            not lo <= v <= hi for lo, v, hi in zip(self.lower, q, self.upper)
        ):
            raise ControlError("joint limit exceeded")


@dataclasses.dataclass(frozen=True)
class State:
    """Controller readback; host receipt never replaces controller uptime."""

    q: Joints
    qd: Joints
    timestamp: float
    received_ns: int
    robot_mode: int = 7
    safety_mode: int = 1
    runtime_state: int = 2

    def __post_init__(self):
        joints(self.q)
        joints(self.qd)
        if type(self.received_ns) is not int or self.received_ns < 0:
            raise ControlError("invalid receipt timestamp")
        if (
            type(self.timestamp) not in (int, float)
            or not math.isfinite(self.timestamp)
            or self.timestamp < 0
        ):
            raise ControlError("invalid controller timestamp")


@dataclasses.dataclass(frozen=True)
class Target:
    """One fresh absolute joint intent, before any command is sent."""

    q: Joints
    sequence: int
    created_ns: int
    source_id: str = "gello"

    def __post_init__(self):
        joints(self.q)
        if not isinstance(self.source_id, str) or not self.source_id:
            raise ControlError("target source identity is required")
        if any(
            type(v) is not int or v < 0
            for v in (self.sequence, self.created_ns)
        ):
            raise ControlError(
                "target sequence and time must be nonnegative integers"
            )


class Transport(Protocol):
    """Only the exclusive owner calls the authorized device transport."""

    def read(self) -> State:
        """Return measured state or raise on a failed read."""

    def move(self, q: Joints, speed: float, acceleration: float) -> None:
        """Begin an asynchronous joint move."""

    def servo(self, q: Joints) -> None:
        """Issue one bounded-duration servo target."""

    def stop(self, servo: bool) -> None:
        """Decelerate without power-off, freedrive or a HOME request."""

    def heartbeat(self) -> None:
        """Kick the controller watchdog from the owning control loop."""

    def close(self) -> None:
        """Release local resources after explicit stop handling."""
