"""Independent archive checks for relative intent and conditioned commands."""

import dataclasses

from ur12e_collection.control import model
from ur12e_collection.leader import episode, mapping


class Audit:
    """Verify raw-to-intent mapping and command bounds from embedded context."""

    def __init__(self, context, started_ns):
        self.calibration = mapping.from_document(context["calibration"])
        if self.calibration.identity() != context["calibration_id"]:
            raise ValueError("leader calibration hash differs")
        self.baseline = self._sample(context["baseline"])
        self.previous = self.baseline
        self.limits = model.Limits(
            **{
                key: (
                    tuple(value)
                    if key in ("lower", "upper", "ready")
                    else value
                )
                for key, value in context["limits"].items()
            }
        )
        if (
            context["mapping"] != "episode_relative"
            or tuple(context["follower_home_rad"]) != self.calibration.home_rad
            or self.limits.ready != self.calibration.home_rad
            or not 0 <= started_ns - self.baseline.start_ns <= 100_000_000
        ):
            raise ValueError("invalid leader baseline context")
        self.command = model.Target(self.limits.ready, 0, started_ns)
        self.velocity = (0.0,) * 6
        self.intent_ns = None
        self.gripper = (
            mapping.GripperReference(**context["gripper_reference"])
            if "gripper_reference" in context
            else None
        )

    @staticmethod
    def _sample(value):
        value = dict(value)
        value["raw"] = tuple(value["raw"])
        value["errors"] = tuple(value["errors"])
        return episode.Sample(**value)

    def intent(self, record):
        """Repeated references may hold fresh input, never refresh its age."""
        sample = self._sample(record.acquisition)
        now = record.provenance.time.source_ns
        if not sample.end_ns <= now <= sample.start_ns + 100_000_000:
            raise ValueError("recorded leader acquisition is stale or future")
        if sample != self.previous:
            if (
                sample.epoch != self.previous.epoch
                or sample.sequence <= self.previous.sequence
                or sample.start_ns < self.previous.end_ns
                or not 0
                < sample.start_ns - self.previous.start_ns
                <= 100_000_000
            ):
                raise ValueError("recorded leader source discontinuity")
        current = self.calibration.angles(sample.raw)
        initial = self.calibration.angles(self.baseline.raw)
        expected = tuple(
            h + q - q0 for h, q, q0 in zip(self.limits.ready, current, initial)
        )
        if model.distance(expected, record.joint_positions_rad) > 1e-12:
            raise ValueError(
                "recorded intent differs from raw relative mapping"
            )
        self.limits.check(expected)
        if (
            self.gripper
            and record.gripper_request_raw
            != self.gripper.position(sample.raw[6])
        ):
            raise ValueError(
                "recorded gripper intent differs from relative mapping"
            )
        self.previous, self.intent_ns = sample, now

    def sent(self, record):
        """Check command derivatives independently of the conditioner code."""
        now = self.intent_ns
        dt = (now - self.command.created_ns) / 1e9
        if not 0 < dt <= self.limits.freshness_ns / 1e9:
            raise ValueError("recorded command generation time invalid")
        q = record.joint_positions_rad
        self.limits.check(q)
        velocity = tuple((a - b) / dt for a, b in zip(q, self.command.q))
        if (
            model.distance(q, self.command.q) > self.limits.step + 1e-10
            or max(map(abs, velocity)) > self.limits.speed + 1e-10
            or max(abs(a - b) / dt for a, b in zip(velocity, self.velocity))
            > self.limits.acceleration + 1e-8
        ):
            raise ValueError("recorded command derivatives exceed limits")
        self.command = dataclasses.replace(self.command, q=q, created_ns=now)
        self.velocity = velocity
