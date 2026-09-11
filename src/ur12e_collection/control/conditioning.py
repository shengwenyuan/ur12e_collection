"""Bound command derivatives while preserving independently recorded intent."""

import math

from ur12e_collection.control import model


class Conditioner:
    """One bounded velocity state per ownership interval; no angle wrapping."""

    def __init__(self, limits, seed: model.Target):
        self.limits = limits
        self.target = seed
        self.velocity = (0.0,) * 6

    def step(self, desired: tuple, now_ns: int) -> model.Target:
        """Generate a command, never a fabricated leader acquisition."""
        self.limits.check(desired)
        dt = (now_ns - self.target.created_ns) / 1e9
        if not 0 < dt <= self.limits.freshness_ns / 1e9:
            raise model.ControlError("conditioner clock stalled or jumped")
        # Reserve numerical headroom for independent finite-difference checks.
        acceleration = self.limits.acceleration * 0.9
        speed = self.limits.speed * 0.9
        positions, velocities = [], []
        for goal, previous, velocity in zip(
            desired, self.target.q, self.velocity
        ):
            error = goal - previous
            requested = math.copysign(
                min(
                    speed, abs(error) / dt, math.sqrt(acceleration * abs(error))
                ),
                error,
            )
            change = max(
                -acceleration * dt,
                min(acceleration * dt, requested - velocity),
            )
            velocity += change
            positions.append(previous + velocity * dt)
            velocities.append(velocity)
        result = model.Target(
            tuple(positions),
            self.target.sequence + 1,
            now_ns,
            self.target.source_id,
        )
        self.limits.check(result.q)
        if model.distance(result.q, self.target.q) > self.limits.step:
            raise model.ControlError("conditioned command step exceeded")
        self.target, self.velocity = result, tuple(velocities)
        return result
