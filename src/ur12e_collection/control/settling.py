"""Measured cancellation policy; the deadline never delays stop dispatch."""

import math

STOP_TIMEOUT_NS = 2_000_000_000
STABLE_NS = 200_000_000
STOP_SPEED = math.radians(0.01)
HOLD_SPEED = math.radians(0.05)
HOLD_DRIFT = math.radians(0.05)
FRESHNESS_NS = 250_000_000


class Standstill:
    """Require low speed across advancing source and host clocks."""

    def __init__(self, freshness_ns: int = FRESHNESS_NS):
        self.freshness_ns = freshness_ns
        self.previous = None
        self.start = None

    def update(self, qd: tuple, source_s: float, now_ns: int) -> bool:
        """Confirm on fresh samples; reset the window on discontinuities."""
        source_ns = round(source_s * 1e9)
        current = (source_ns, now_ns)
        if self.previous is not None:
            gaps = tuple(b - a for a, b in zip(self.previous, current))
            if min(gaps) < 0 or max(gaps) > self.freshness_ns:
                self.start = None
            elif min(gaps) == 0:
                return False
        self.previous = current
        if len(qd) != 6 or not all(
            math.isfinite(v) and abs(v) <= STOP_SPEED for v in qd
        ):
            self.start = None
            return False
        if self.start is None:
            self.start = current
        return all(b - a >= STABLE_NS for a, b in zip(self.start, current))
