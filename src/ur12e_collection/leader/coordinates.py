"""Explicit coordinate binding after a verified stationary torque transition."""

import dataclasses

from ur12e_collection.leader import mapping


@dataclasses.dataclass(frozen=True)
class PoweredAxis:
    """A measured logical/goal offset, valid only within one powered epoch."""

    epoch: str
    logical_count: int
    powered_count: int
    minimum: int
    maximum: int

    def __post_init__(self):
        if not isinstance(self.epoch, str) or not self.epoch.strip():
            raise ValueError("powered coordinate epoch required")
        for value in (
            self.logical_count,
            self.powered_count,
            self.minimum,
            self.maximum,
        ):
            mapping.integer(value)
        if not (
            mapping.MIN_COUNT <= self.logical_count <= mapping.MAX_COUNT
            and 0 <= self.minimum <= self.powered_count <= self.maximum <= 4095
            and self.minimum < self.maximum
        ):
            raise ValueError("invalid powered coordinate binding")

    def goal(self, logical: int, epoch: str) -> int:
        """Translate without modulo; a reset always requires another binding."""
        mapping.integer(logical)
        if epoch != self.epoch:
            raise ValueError("powered coordinate epoch changed")
        goal = self.powered_count + logical - self.logical_count
        if not self.minimum <= goal <= self.maximum:
            raise ValueError("powered goal outside configured interval")
        return goal
