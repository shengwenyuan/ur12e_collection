"""Monotonic periodic scheduling shared by acquisition and control."""


def next_deadline(previous: int, now: int, period: int) -> int:
    """Preserve phase and skip expired slots without catch-up bursts."""
    deadline = previous + period
    if deadline <= now:
        deadline += ((now - deadline) // period + 1) * period
    return deadline
