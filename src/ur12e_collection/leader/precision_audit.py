"""Independent reconstruction of height mapping and conditioned commands."""

import math

from ur12e_collection.control import model, precision


class Audit:
    """Check archive evidence without invoking the runtime mapping algorithm."""

    def __init__(self, document, limits):
        self.profile = precision.from_document(document)
        self.limits = limits
        self.reference = limits.ready
        self.feedback = None
        self.gain = 1.0

    def intent(self, record, delta, command, velocity):
        """Recompute height, gain, incremental intent and anti-windup state."""
        state = record.mapping_state
        if state is None or set(state) != {
            "feedback",
            "z_m",
            "gain",
            "accepted",
        }:
            raise ValueError("precision mapping evidence missing or invalid")
        now = record.provenance.time.source_ns
        gain = self._gain(state, now)
        expected = tuple(q + gain * d for q, d in zip(self.reference, delta))
        if model.distance(expected, record.joint_positions_rad) > 1e-12:
            raise ValueError("precision incremental intent differs")
        self.limits.check(expected)
        dt = (now - command.created_ns) / 1e9
        if not 0 < dt <= self.limits.freshness_ns / 1e9:
            raise ValueError("precision command time invalid")
        accepted = self._contract(expected, command, velocity, dt, gain)
        actual = tuple(state["accepted"])
        self.limits.check(actual)
        if model.distance(tuple(accepted), actual) > 1e-10:
            raise ValueError("precision pending-target correction differs")
        self.reference, self.feedback, self.gain = (
            actual,
            state["feedback"],
            gain,
        )
        return expected

    def _gain(self, state, now):
        """Check the pinned height basis and source freshness independently."""
        feedback = state["feedback"]
        if (
            feedback["source_clock"]
            not in (
                "ur_controller_uptime",
                "isaac_physics_simulation",
                "isaac_kinematic_monotonic",
            )
            or self.feedback is not None
            and feedback["source_clock"] != self.feedback["source_clock"]
        ):
            raise ValueError(
                "precision feedback clock invalid or source changed"
            )
        q = tuple(feedback["q"])
        self.limits.check(q)
        if (
            not 0
            <= now - feedback["received_ns"]
            <= min(self.limits.freshness_ns, 100_000_000)
            or not math.isfinite(feedback["timestamp"])
            or feedback["timestamp"] < 0
        ):
            raise ValueError("precision feedback is stale or invalid")
        if self.feedback is not None and (
            feedback["timestamp"] < self.feedback["timestamp"]
            or feedback["received_ns"] < self.feedback["received_ns"]
            or (
                feedback["timestamp"] == self.feedback["timestamp"]
                and feedback != self.feedback
            )
        ):
            raise ValueError("precision feedback source changed or reset")
        z = float(self.profile.geometry.position(q)[2])
        settings = self.profile.settings
        h = z - settings.reference_z_m
        knots = settings.knots
        gain = knots[0][1]
        for (lo, a), (hi, b) in zip(knots, knots[1:]):
            gain += (b - a) * max(0, min(1, (h - lo) / (hi - lo)))
        if (
            not all(math.isfinite(state[k]) for k in ("z_m", "gain"))
            or abs(z - state["z_m"]) > 1e-12
            or abs(gain - state["gain"]) > 1e-12
        ):
            raise ValueError("precision height or gain differs")
        return gain

    # Keep independently derived scalar bounds explicit for audit review.
    # pylint: disable-next=too-many-locals
    def _contract(self, expected, command, velocity, dt, gain):
        """Reconstruct the feasible interval and exponential correction."""
        settings = self.profile.settings
        knots = settings.knots
        lead = self.limits.speed * 0.9 * gain * settings.lead_seconds
        acceleration = self.limits.acceleration * 0.9 * knots[0][1]
        decay = math.exp(-dt / settings.correction_seconds)
        accepted = []
        for target, q, v in zip(expected, command.q, velocity):
            displacement = v * abs(v) / acceleration
            lo = q + min(0, displacement) - lead
            hi = q + max(0, displacement) + lead
            clipped = min(hi, max(lo, target))
            accepted.append(clipped + decay * (target - clipped))
        return accepted

    def sent(self, q, command, velocity, dt):
        """Check the command against the independently restored target."""
        a = self.limits.acceleration * 0.9 * self.gain
        speed = self.limits.speed * 0.9 * self.gain
        expected = []
        for target, before, v in zip(self.reference, command.q, velocity):
            error = target - before
            desired_v = math.copysign(
                min(speed, abs(error) / dt, math.sqrt(a * abs(error))), error
            )
            following_v = min(v + a * dt, max(v - a * dt, desired_v))
            expected.append(before + following_v * dt)
        if model.distance(tuple(expected), q) > 1e-10:
            raise ValueError("precision conditioned command differs")
