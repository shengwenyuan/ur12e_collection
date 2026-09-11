"""Recorded encoder replay, with no serial-device fallback."""

import bisect
import hashlib
import json
import pathlib

from ur12e_collection.leader import episode, input as leader_input, mapping


class Trace:
    """Replay immutable samples using one local monotonic clock domain."""

    def __init__(
        self, path: pathlib.Path, *, reference_sequence=273, speed=1.0
    ):
        if not 0 < speed <= 4:
            raise ValueError("replay speed must be in (0, 4]")
        payload = path.read_bytes()
        self.rows = [json.loads(line) for line in payload.splitlines()]
        for previous, current in zip(self.rows, self.rows[1:]):
            if (
                current["sequence"] != previous["sequence"] + 1
                or current["epoch"] != previous["epoch"]
                or current["start_ns"] <= previous["end_ns"]
                or any(current["errors"])
            ):
                raise ValueError("invalid source trace chronology")
        self.reference = reference_sequence
        if not 3 <= self.reference < len(self.rows) - 1:
            raise ValueError("reference needs three preceding samples")
        self.speed = speed
        self.identity = hashlib.sha256(payload).hexdigest()
        self.origin = {
            "kind": "recorded_leader_replay",
            "sha256": self.identity,
            "reference_sequence": reference_sequence,
            "speed": speed,
            "physical_direction_verified": False,
        }
        self.started_ns = None
        self.epoch = None
        self.times = []

    def start(self, now_ns):
        """Start a new replay epoch at the recorded reference."""
        self.started_ns = now_ns
        self.epoch = f"replay:{self.identity}:{now_ns}"
        origin = self.rows[self.reference]["end_ns"]
        # Keep the stable reference window; accelerate only later input.
        self.times = [
            now_ns
            + round(
                (row["end_ns"] - origin)
                / (1 if index <= self.reference else self.speed)
            )
            for index, row in enumerate(self.rows)
        ]
        return self

    def samples(self, now_ns):
        """Return actual trace values; exhaustion remains a source failure."""
        index = bisect.bisect_right(self.times, now_ns) - 1
        if index < self.reference or now_ns - self.times[index] > 100_000_000:
            raise ValueError("leader replay exhausted or stale")
        result = []
        for i in range(max(0, index - 3), index + 1):
            row = self.rows[i]
            # Scheduled replay availability is distinct from original USB time.
            result.append(
                episode.Sample(
                    self.epoch,
                    row["sequence"],
                    self.times[i] - 1,
                    self.times[i],
                    tuple(row["position"]),
                    tuple(row["errors"]),
                )
            )
        return tuple(result)

    def calibration(self, home):
        """Test-only intervals/signs; these never attest physical alignment."""
        raw = self.rows[self.reference]["position"]
        signs = (1, -1, 1, 1, 1, 1)
        return mapping.Calibration(
            home,
            tuple(
                mapping.Joint(value, sign, value - 2048, value + 2048)
                for value, sign in zip(raw[:6], signs)
            ),
            3256,
            3388,
            "operator reference; simulation direction candidates",
            self.identity,
        )

    def factory(self, limits):
        """Inject shared mapping and conditioning into a control session."""
        calibration = self.calibration(limits.ready)

        def create(follower, now_ns):
            return leader_input.Input(
                self.start(now_ns), calibration, limits, follower, now_ns
            )

        return create
