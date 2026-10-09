"""Deliberate operator inputs; no fixture enters the production input path."""

import math

DURATIONS = {"sweep": 32, "reversal": 24, "deep": 32, "noise": 32}


def lerp(t, knots):
    for (start, a), (end, b) in zip(knots, knots[1:]):
        if t < end:
            return a + (b - a) * max(0, (t - start) / (end - start))
    return knots[-1][1]


def trajectory(t, case="sweep"):
    """Cover full gain range, pending-motion reversal and the original descent."""
    deep = case == "deep"
    shoulder = lerp(
        t,
        (
            (0, 0),
            (4, -0.18 if deep else -0.10),
            (6, -0.18 if deep else -0.10),
            (10, 0.08),
            (12, 0.08),
            (16, -0.20 if deep else -0.12),
            (18, -0.20 if deep else -0.12),
            (22, 0.10),
            (32, 0.10),
        ),
    )
    base_knots = (
        (0, 0),
        (2, 0),
        (2.3, 0.40),
        (5, 0.40),
        (5.7, -0.25),
        (9, -0.25),
        (11, 0),
        (32, 0),
    )
    if case == "reversal":
        shoulder = 0
        base_knots = (
            (0, 0),
            (2, 0),
            (2.3, 0.4),
            (2.4, 0.4),
            (3, -0.3),
            (8, -0.3),
            (8.5, 0.25),
            (8.6, 0.25),
            (9.2, -0.25),
            (16, -0.25),
            (17, 0),
            (24, 0),
        )
    base = lerp(t, base_knots)
    elbow = (
        0.02 * math.sin(math.pi * min(t, 22) / 11) if case != "reversal" else 0
    )
    wrist = (
        0.025 * math.sin(math.pi * min(t, 22) / 11) if case != "reversal" else 0
    )
    if case == "noise":
        amplitude = lerp(t, ((0, 0), (2, 0), (4, 1), (20, 1), (22, 0)))
        shoulder = amplitude * (-0.07 + 0.004 * math.sin(2 * math.pi * 0.8 * t))
        base = amplitude * 0.003 * math.sin(2 * math.pi * 1.3 * t)
    return (base, shoulder, elbow, -shoulder - elbow, wrist, -wrist)
