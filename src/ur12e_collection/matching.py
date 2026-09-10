"""Deterministic wrist-anchored matching without hardware or background work."""

import collections
import dataclasses
from typing import Any

from ur12e_collection import contracts

RGB_TIME_QUANTUM_NS = 1000


def _integer(value: int) -> None:
    if (not isinstance(value, int) or isinstance(value, bool)) or value < 0:
        raise ValueError(
            "timestamps, counters and generations must be integers"
        )


@dataclasses.dataclass(frozen=True)
class Frame:
    """One aligned RGB-D pair on an explicitly established common clock."""

    role: str
    generation: int
    clock_id: str
    timestamp_ns: int
    color: contracts.Provenance
    depth: contracts.Provenance
    depth_timestamp_ns: int
    payload: Any = dataclasses.field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.role not in contracts.CAMERA_ROLES or not self.clock_id:
            raise ValueError(
                "a camera role and established common clock are required"
            )
        _integer(self.generation)
        _integer(self.timestamp_ns)
        _integer(self.depth_timestamp_ns)
        if not all(
            isinstance(p, contracts.Provenance)
            for p in (self.color, self.depth)
        ):
            raise ValueError("color and depth provenance are required")
        if (self.color.source_id, self.color.simulated) != (
            self.depth.source_id,
            self.depth.simulated,
        ):
            raise ValueError("RGB-D members must belong to the same source")

    def metadata(self) -> dict:
        """Return acquisition provenance without copying image payloads."""
        return {
            field.name: (
                dataclasses.asdict(getattr(self, field.name))
                if field.name in ("color", "depth")
                else getattr(self, field.name)
            )
            for field in dataclasses.fields(self)
            if field.name != "payload"
        }


@dataclasses.dataclass(frozen=True)
class Match:
    """An accepted triple or an explicit rejection for one wrist anchor."""

    anchor: Frame
    members: tuple[Frame, ...]
    reason: str
    decided_ns: int

    @property
    def accepted(self) -> bool:
        """Whether all three real members were selected."""
        return self.reason == "accepted"

    def metadata(self) -> dict:
        """Preserve anchor, individual source times and signed member skews."""
        return {
            "schema_version": 1,
            "reason": self.reason,
            "anchor": self.anchor.metadata(),
            "members": [frame.metadata() for frame in self.members],
            "skews_ns": {
                f.role: f.timestamp_ns - self.anchor.timestamp_ns
                for f in self.members
            },
            "decided_monotonic_ns": self.decided_ns,
        }


@dataclasses.dataclass(frozen=True)
class MatchConfig:
    """Aligned limits; latency uses host monotonic time, not camera clocks."""

    max_skew_ns: int = 16_700_000
    wait_ns: int = 75_000_000
    capacity: int = 8

    def __post_init__(self) -> None:
        for value in dataclasses.astuple(self):
            _integer(value)
        if self.capacity == 0:
            raise ValueError("buffer capacity must be positive")


def freshness(frame: Frame, previous: Frame | None) -> str:
    """Shared accepted-stream rule, including encoder time resolution."""
    if previous is None:
        return "accepted"
    if (
        frame.color.sequence <= previous.color.sequence
        or frame.depth.sequence <= previous.depth.sequence
    ):
        return "frame_reuse"
    if (
        frame.timestamp_ns - previous.timestamp_ns < RGB_TIME_QUANTUM_NS
        or frame.depth_timestamp_ns <= previous.depth_timestamp_ns
    ):
        return "invalid_timing"
    return "accepted"


class SourceFault(RuntimeError):
    """A blocked source generation and its pending rejected wrist anchors."""

    def __init__(self, generation: int, rejections: list[Match]):
        super().__init__("matcher source fault; explicit reset required")
        self.generation = generation
        self.rejections = tuple(rejections)


class Matcher:
    """Bounded online greedy matcher; source discontinuities require reset."""

    def __init__(self, clock_id: str, config: MatchConfig = MatchConfig()):
        if not isinstance(clock_id, str) or not clock_id:
            raise ValueError("an established common clock is required")
        self.clock_id = clock_id
        self.config = config
        self.counters = collections.Counter()
        self._buffers = {r: collections.deque() for r in contracts.CAMERA_ROLES}
        self._last: dict[str, Frame] = {}
        self._used: dict[str, Frame] = {}
        self._now = 0
        self._blocked = False
        self._generation = 0

    def _time(self, now_ns: int) -> None:
        _integer(now_ns)
        if now_ns < self._now:
            raise ValueError("host monotonic time moved backwards")
        self._now = now_ns

    def _valid_source(self, frame: Frame) -> bool:
        if (
            frame.clock_id != self.clock_id
            or frame.generation != self._generation
        ):
            return False
        for role, previous in self._last.items():
            if previous.color.simulated != frame.color.simulated:
                return False
            if (
                role != frame.role
                and previous.color.source_id == frame.color.source_id
            ):
                return False
        previous = self._last.get(frame.role)
        if previous is None:
            return True
        return (
            frame.generation == previous.generation
            and frame.color.source_id == previous.color.source_id
            and frame.timestamp_ns > previous.timestamp_ns
            and frame.color.sequence > previous.color.sequence
            and frame.depth.sequence >= previous.depth.sequence
        )

    def _reject(self, anchor: Frame, reason: str) -> Match:
        self.counters[reason] += 1
        return Match(anchor, (), reason, self._now)

    def reset(self, generation: int) -> list[Match]:
        """Explicitly discard pending work before accepting a new generation."""
        _integer(generation)
        if generation <= self._generation:
            raise ValueError("reset requires a newer source generation")
        result = self._invalidate("reset")
        self._generation = generation
        self._blocked = False
        return result

    def _invalidate(self, reason: str) -> list[Match]:
        result = [self._reject(f, reason) for f in self._buffers["wrist"]]
        for buffer in self._buffers.values():
            buffer.clear()
        self._last.clear()
        self._used.clear()
        return result

    def push(self, frame: Frame, now_ns: int) -> list[Match]:
        """Supply a frame; late arrivals cannot rescue an expired anchor."""
        self._time(now_ns)
        if self._blocked:
            raise SourceFault(self._generation, [])
        if frame.color.time.received_monotonic_ns > now_ns:
            raise ValueError("frame receipt is in the future")
        if not self._valid_source(frame):
            result = self._invalidate("source_fault")
            self._blocked = True
            self.counters["source_fault_events"] += 1
            raise SourceFault(self._generation, result)
        result = self._drain(strict_deadline=True)
        self._last[frame.role] = dataclasses.replace(frame, payload=None)
        self._prune()
        buffer = self._buffers[frame.role]
        if len(buffer) == self.config.capacity:
            evicted = buffer.popleft()
            self.counters[f"overflow_{frame.role}"] += 1
            if frame.role == "wrist":
                result.append(self._reject(evicted, "overflow"))
        buffer.append(frame)
        return result + self._drain()

    def advance(self, now_ns: int) -> list[Match]:
        """Resolve anchors when their bounded waiting window expires."""
        self._time(now_ns)
        return self._drain()

    def finish(self, now_ns: int) -> list[Match]:
        """Resolve remaining anchors using only frames already received."""
        self._time(now_ns)
        result = self._drain(force=True)
        for buffer in self._buffers.values():
            buffer.clear()
        return result

    def _select(self, anchor: Frame, role: str) -> tuple[Frame | None, str]:
        buffer = self._buffers[role]
        candidates = [
            f
            for f in buffer
            if abs(f.timestamp_ns - anchor.timestamp_ns)
            <= self.config.max_skew_ns
        ]
        if not candidates:
            return None, "missing_view" if not buffer else "excessive_skew"
        reasons = [freshness(f, self._used.get(role)) for f in candidates]
        eligible = [
            f for f, reason in zip(candidates, reasons) if reason == "accepted"
        ]
        if not eligible:
            return None, (
                "invalid_timing"
                if "invalid_timing" in reasons
                else "frame_reuse"
            )
        return (
            min(
                eligible,
                key=lambda f: (
                    abs(f.timestamp_ns - anchor.timestamp_ns),
                    f.timestamp_ns,
                ),
            ),
            "accepted",
        )

    def _prune(self) -> None:
        """Retire frames too old for any pending or future wrist anchor."""
        pending = self._buffers["wrist"]
        anchor = pending[0] if pending else self._last.get("wrist")
        if anchor is None:
            return
        earliest = anchor.timestamp_ns - self.config.max_skew_ns
        for role in contracts.CAMERA_ROLES[1:]:
            buffer = self._buffers[role]
            while buffer and buffer[0].timestamp_ns < earliest:
                buffer.popleft()
                self.counters[f"expired_{role}"] += 1

    def _decide(self, anchor: Frame) -> Match:
        reason = freshness(anchor, self._used.get("wrist"))
        if reason != "accepted":
            return self._reject(anchor, reason)
        members = [anchor]
        for role in contracts.CAMERA_ROLES[1:]:
            member, reason = self._select(anchor, role)
            if member is None:
                return self._reject(anchor, reason)
            members.append(member)
        for member in members:
            self._used[member.role] = dataclasses.replace(member, payload=None)
        self.counters["accepted"] += 1
        return Match(anchor, tuple(members), "accepted", self._now)

    def _drain(
        self, *, force: bool = False, strict_deadline: bool = False
    ) -> list[Match]:
        result = []
        while self._buffers["wrist"]:
            anchor = self._buffers["wrist"][0]
            deadline = (
                anchor.color.time.received_monotonic_ns + self.config.wait_ns
            )
            expired = (
                self._now > deadline
                if strict_deadline
                else self._now >= deadline
            )
            ready = all(
                r in self._last
                and self._last[r].timestamp_ns >= anchor.timestamp_ns
                for r in contracts.CAMERA_ROLES[1:]
            )
            if not (force or expired or ready):
                break
            result.append(self._decide(self._buffers["wrist"].popleft()))
        return result
