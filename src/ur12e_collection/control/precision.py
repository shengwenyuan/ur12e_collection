"""Continuous height gain and bounded, non-repayable input accumulation."""

import dataclasses
import math
import pathlib

from ur12e_collection.control import model


@dataclasses.dataclass(frozen=True)
class Settings:
    """Meters, dimensionless gain and seconds; no physical safety claim."""

    reference_z_m: float
    knots: tuple
    lead_seconds: float
    correction_seconds: float

    def __post_init__(self):
        values = (
            self.reference_z_m,
            self.lead_seconds,
            self.correction_seconds,
            *(v for k in self.knots for v in k),
        )
        if any(
            type(v) not in (int, float) or not math.isfinite(v) for v in values
        ):
            raise ValueError("precision settings must be finite numbers")
        if self.lead_seconds <= 0 or self.correction_seconds <= 0:
            raise ValueError("precision time constants must be positive")
        if (
            len(self.knots) < 2
            or any(len(k) != 2 for k in self.knots)
            or any(not 0 < gain <= 1 for _, gain in self.knots)
            or any(
                a[0] >= b[0] or a[1] >= b[1]
                for a, b in zip(self.knots, self.knots[1:])
            )
        ):
            raise ValueError("invalid precision schedule or time constants")

    def gain(self, z):
        """Interpolate the agreed knots continuously in either direction."""
        h = z - self.reference_z_m
        if h <= self.knots[0][0]:
            return self.knots[0][1]
        for (lo, a), (hi, b) in zip(self.knots, self.knots[1:]):
            if h < hi:
                return a + (b - a) * (h - lo) / (hi - lo)
        return self.knots[-1][1]


class Profile:
    """Preloaded geometry and immutable settings shared by all intervals."""

    def __init__(self, settings, geometry, path=None):
        self.settings, self.geometry, self.path = settings, geometry, path

    def document(self):
        """Embed pinned geometry once for independent archive verification."""
        return {
            "settings": dataclasses.asdict(self.settings),
            "urdf": self.geometry.source.decode(),
            "sha256": self.geometry.sha256,
        }

    def observe(self, feedback, now_ns, freshness_ns):
        """Use only fresh actual joint feedback, never a desired pose."""
        if feedback is None or not 0 <= now_ns - feedback.received_ns <= min(
            freshness_ns, 100_000_000
        ):
            raise model.ControlError("precision feedback is stale or missing")
        z = float(self.geometry.position(feedback.q)[2])
        return {
            "feedback": {
                "q": feedback.q,
                "timestamp": feedback.timestamp,
                "received_ns": feedback.received_ns,
                "source_clock": getattr(
                    feedback, "source_clock", "ur_controller_uptime"
                ),
            },
            "z_m": z,
            "gain": self.settings.gain(z),
        }

    def correct(self, candidate, conditioner, gain, dt):
        """Contract excess lead without pulling it behind the braking point."""
        speed = 0.9 * conditioner.limits.speed * gain
        # The conditioner uses sqrt(a * distance), a conservative braking law.
        # Cover its stopping envelope at the lowest scheduled acceleration.
        acceleration = (
            0.9 * conditioner.limits.acceleration * self.settings.knots[0][1]
        )
        lead = speed * self.settings.lead_seconds
        beta = -math.expm1(-dt / self.settings.correction_seconds)
        accepted = []
        for desired, q, v in zip(
            candidate, conditioner.target.q, conditioner.velocity
        ):
            brake = q + v * abs(v) / acceleration
            feasible = max(
                min(q, brake) - lead, min(max(q, brake) + lead, desired)
            )
            accepted.append(desired + beta * (feasible - desired))
        return tuple(accepted)


def from_document(value):
    """Restore and validate the exact embedded geometry and schedule."""
    # NumPy is needed only when this opt-in feature is selected.
    # pylint: disable-next=import-outside-toplevel
    from ur12e_collection.control import kinematics

    settings = dict(value["settings"])
    settings["knots"] = tuple(tuple(k) for k in settings["knots"])
    return Profile(
        Settings(**settings),
        kinematics.Kinematics(value["urdf"].encode(), value["sha256"]),
    )


def load(value, base):
    """Select the mapping before loading any optional geometry."""
    value = dict(value)
    enabled = value.pop("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("precision.enabled must be a Boolean")
    if not enabled:
        return None
    path = (base / pathlib.Path(value.pop("urdf")).expanduser()).resolve()
    sha256 = value.pop("sha256")
    profile = from_document(
        {
            "settings": value,
            "sha256": sha256,
            "urdf": path.read_text(encoding="utf-8"),
        }
    )
    profile.path = path
    return profile
