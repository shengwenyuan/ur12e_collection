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
    gripper_input_rate: float = math.radians(720)

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
        if dt <= 0:
            raise model.ControlError("leader acquisition time did not advance")
        radians_per_count = 2 * math.pi / 4096
        rates = (self.input_rate,) * 6 + (self.gripper_input_rate,)
        for axis, (before, after, rate) in enumerate(
            zip(previous.raw, current.raw, rates)
        ):
            allowance = rate * dt / radians_per_count + 2
            delta = abs(after - before)
            if delta > allowance:
                name = "gripper" if axis == 6 else f"j{axis + 1}"
                raise model.ControlError(
                    f"leader acquisition jumped: axis={name}, "
                    f"previous={before}, current={after}, "
                    f"delta_counts={delta}, allowed_counts={allowance:.2f}, "
                    f"dt_ms={dt * 1000:.3f}; reinitialize"
                )

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
