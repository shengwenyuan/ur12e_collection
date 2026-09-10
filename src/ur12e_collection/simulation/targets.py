"""Synthetic leader fixtures only; independent of the real GELLO adapter."""

import math

from ur12e_collection.control.model import Target


class Wave:
    """Start at the measured seed with zero initial target velocity."""

    def __init__(self, seed: tuple, start_ns: int):
        self.seed = seed
        self.start_ns = start_ns
        self.sequence = 0

    def sample(self, now_ns: int) -> Target:
        """Generate asymmetric smooth joint intent with explicit host time."""
        elapsed = (now_ns - self.start_ns) / 1e9
        amplitude = (0.35, 0.20, 0.24, 0.30, 0.22, 0.40)
        frequency = (0.10, 0.13, 0.09, 0.12, 0.15, 0.11)
        q = tuple(
            seed + a * (1 - math.cos(2 * math.pi * f * elapsed))
            for seed, a, f in zip(self.seed, amplitude, frequency)
        )
        target = Target(q, self.sequence, now_ns, "simulation-wave")
        self.sequence += 1
        return target
