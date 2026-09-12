"""Separate source plausibility, queued intent and executed tracking bounds."""

import dataclasses
import math

from ur12e_collection.control import model


@dataclasses.dataclass(frozen=True)
class Policy:
    """Radians and seconds; optional for existing simulator profiles."""

    input_rate: float
    intent_error: float
    tracking_error: float
    tracking_seconds: float
    measured_speed: float

    def __post_init__(self):
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError("guard limits must be finite positive numbers")

    def input(self, previous, current):
        """Reject raw jumps before smoothing, including the gripper encoder."""
        dt = (current.start_ns - previous.start_ns) / 1e9
        allowance = self.input_rate * dt + 2 * 2 * math.pi / 4096
        delta = max(abs(a - b) for a, b in zip(current.raw, previous.raw))
        if dt <= 0 or delta * 2 * math.pi / 4096 > allowance:
            raise model.ControlError("leader acquisition jumped; reinitialize")

    def intent(self, desired, sent):
        """Bound delayed motion without changing the immutable input origin."""
        if model.distance(desired, sent) > self.intent_error:
            raise model.ControlError(
                "leader outran command; stop and reinitialize"
            )


class Tracking:
    """Require sustained tracking error on advancing measured samples."""

    def __init__(self, policy):
        self.policy = policy
        self.since = None

    def check(self, target, feedback, now_ns):
        """Check actual overspeed and command/readback divergence."""
        if max(map(abs, feedback.qd)) > self.policy.measured_speed:
            raise model.ControlError("actual joint speed exceeded test limit")
        if model.distance(target, feedback.q) <= self.policy.tracking_error:
            self.since = None
        elif self.since is None:
            self.since = (now_ns, feedback.timestamp)
        elif (
            now_ns - self.since[0] >= self.policy.tracking_seconds * 1e9
            and feedback.timestamp - self.since[1]
            >= self.policy.tracking_seconds
        ):
            raise model.ControlError("follower tracking error persisted")
