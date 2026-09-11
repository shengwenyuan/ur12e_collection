"""Stateful motor fixture with torque reset, lag and failure injection."""

import dataclasses
import time

from ur12e_collection.leader import coordinates, motion


class Motors:
    """No SDK or serial access; intentionally not a gravity/thermal model."""

    def __init__(self, counts=(2048,) * 7, *, realtime=False):
        self.value = motion.State("fixture-0", tuple(counts), (False,) * 7, 0)
        self.goal = list(counts)
        self.writes = []
        self.generation = 0
        self.residual = 0
        self.closed = False
        self.realtime = realtime

    def advance(self, now_ns):
        """Advance a bounded fixture response without physical dynamics."""
        counts = list(self.value.counts)
        for index, enabled in enumerate(self.value.torque):
            if enabled:
                difference = self.goal[index] + self.residual - counts[index]
                counts[index] += max(-25, min(25, difference))
        self.value = dataclasses.replace(
            self.value, counts=tuple(counts), received_ns=now_ns
        )

    def read(self, now_ns=None):
        """Return simulated measurements, optionally advancing the fixture."""
        if self.closed:
            raise RuntimeError("fixture closed")
        if self.realtime:
            self.advance(time.monotonic_ns() if now_ns is None else now_ns)
        return self.value

    def goals(self, goals):
        """Record exact requested goals independently of measured counts."""
        self.writes.append(("goals", dict(goals)))
        for motor_id, goal in goals.items():
            self.goal[motor_id - 1] = goal

    def enable(self, ids):
        """Simulate the documented single-turn reset when enabling torque."""
        self.writes.append(("enable", ids))
        torque = list(self.value.torque)
        counts = list(self.value.counts)
        for motor_id in ids:
            torque[motor_id - 1] = True
            counts[motor_id - 1] %= 4096
        self.generation += 1
        self.value = dataclasses.replace(
            self.value,
            torque=tuple(torque),
            counts=tuple(counts),
            epoch=f"fixture-{self.generation}",
        )

    def disable(self, ids):
        """Model explicit manual-leading release and its new epoch."""
        self.writes.append(("disable", ids))
        torque = list(self.value.torque)
        for motor_id in ids:
            torque[motor_id - 1] = False
        self.generation += 1
        self.value = dataclasses.replace(
            self.value, torque=tuple(torque), epoch=f"fixture-{self.generation}"
        )

    def bindings(self):
        """Provide fixture-known encoder branches, not physical evidence."""
        return tuple(
            coordinates.PoweredAxis(
                self.value.epoch, count, count % 4096, 0, 4095
            )
            for count in self.value.counts
        )

    def close(self):
        """Close fixture access without changing torque or position."""
        self.closed = True
