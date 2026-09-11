"""Episode-relative intent with immutable references and latched faults."""

import dataclasses

from ur12e_collection.control import model
from ur12e_collection.leader import mapping


@dataclasses.dataclass(frozen=True)
class Sample:
    """One real acquisition in a source epoch, using the owner's host clock."""

    epoch: str
    sequence: int
    start_ns: int
    end_ns: int
    raw: tuple[int, ...]
    errors: tuple[int, ...] = (0,) * 7

    def __post_init__(self):
        if not isinstance(self.epoch, str) or not self.epoch.strip():
            raise ValueError("source epoch is required")
        for value in (self.sequence, self.start_ns, self.end_ns):
            mapping.integer(value)
            if value < 0:
                raise ValueError("negative sample sequence or time")
        if self.end_ns < self.start_ns:
            raise ValueError("sample acquisition time runs backward")
        if (
            not isinstance(self.raw, tuple)
            or len(self.raw) != 7
            or not isinstance(self.errors, tuple)
            or len(self.errors) != 7
        ):
            raise ValueError("seven immutable raw values and errors required")
        for value in self.raw + self.errors:
            mapping.integer(value)
        if any(self.errors):
            raise ValueError("motor status error")


def _fresh(sample, now_ns, age_ns):
    mapping.integer(now_ns)
    if not sample.start_ns <= sample.end_ns <= now_ns:
        raise ValueError("future or invalid sample time")
    if now_ns - sample.start_ns > age_ns:
        raise ValueError("stale leader sample")


def check_advance(previous, current, age_ns):
    """Validate source continuity without wrapping or inventing samples."""
    if previous.epoch != current.epoch:
        raise ValueError("source epoch changed; new engagement required")
    if (
        current.sequence <= previous.sequence
        or current.start_ns < previous.end_ns
        or current.start_ns <= previous.start_ns
    ):
        raise ValueError("repeated or reordered leader stream")
    gap_ns = current.start_ns - previous.start_ns
    if gap_ns > age_ns:
        raise ValueError(
            f"interrupted leader stream: {gap_ns / 1e6:.3f} ms gap "
            f"exceeds {age_ns / 1e6:.3f} ms "
            f"(sequence {previous.sequence} to {current.sequence})"
        )


class EpisodeMapper:
    """Generate absolute follower intents; never contact or control a device."""

    # Explicit rehearsal timing policy; the production default stays 100 ms.
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        calibration,
        limits,
        samples,
        follower,
        now_ns,
        *,
        freshness_ns=100_000_000,
    ):
        self._calibration = calibration
        self._limits = limits
        mapping.integer(freshness_ns)
        if freshness_ns <= 0:
            raise ValueError("input freshness must be positive")
        self._age_ns = min(limits.freshness_ns, freshness_ns)
        self._fault = None
        if calibration.home_rad != limits.ready:
            raise ValueError("calibration and follower HOME differ")
        if (
            not 0 <= now_ns - follower.received_ns <= self._age_ns
            or max(abs(v) for v in follower.qd) > limits.stopped_speed
            or model.distance(follower.q, limits.ready) > limits.arrival
            or model.distance(follower.q, limits.ready) > limits.step
        ):
            raise ValueError("fresh stationary follower HOME required")
        limits.check(follower.q)
        self._reference(samples, now_ns)
        self._baseline = samples[-1]
        self._last = samples[-1]
        self._follower = follower

    def _reference(self, samples, now_ns):
        if len(samples) < 3:
            raise ValueError("at least three stable startup samples required")
        for index, sample in enumerate(samples):
            _fresh(sample, now_ns, self._age_ns)
            self._calibration.angles(sample.raw)
            self._calibration.gripper(sample.raw[6])
            if index:
                check_advance(samples[index - 1], sample, self._age_ns)
        if samples[-1].start_ns - samples[0].start_ns < 40_000_000:
            raise ValueError("startup reference must span at least 40 ms")
        if any(max(v) - min(v) > 2 for v in zip(*(s.raw for s in samples))):
            raise ValueError("leader startup reference is moving")

    def context(self) -> dict:
        """Return a detached record for immutable episode metadata."""
        return {
            "mapping": "episode_relative",
            "schema_version": 1,
            "calibration_id": self._calibration.identity(),
            "baseline": dataclasses.asdict(self._baseline),
            "baseline_calibrated_rad": self._calibration.angles(
                self._baseline.raw
            ),
            "follower_home_rad": self._limits.ready,
            "follower_start": dataclasses.asdict(self._follower),
        }

    def first(self) -> model.Target:
        """Zero delta starts at configured HOME, retaining the source time."""
        self._healthy()
        return model.Target(
            self._limits.ready,
            self._baseline.sequence,
            self._baseline.start_ns,
            "gello",
        )

    def _healthy(self):
        if self._fault is not None:
            raise model.ControlError(f"episode mapping stopped: {self._fault}")

    def target(self, sample: Sample, now_ns: int) -> model.Target:
        """Reject bad input permanently; no catch-up, rebase or integration."""
        self._healthy()
        try:
            _fresh(sample, now_ns, self._age_ns)
            check_advance(self._last, sample, self._age_ns)
            current = self._calibration.angles(sample.raw)
            start = self._calibration.angles(self._baseline.raw)
            self._calibration.gripper(sample.raw[6])
            desired = tuple(
                home + q - q0
                for home, q, q0 in zip(self._limits.ready, current, start)
            )
            self._limits.check(desired)
            target = model.Target(desired, sample.sequence, sample.start_ns)
            self._last = sample
            return target
        except (ValueError, model.ControlError) as error:
            self._fault = str(error)
            raise model.ControlError(str(error)) from error

    def stop(self) -> None:
        """Retire the reference; another episode requires a new one."""
        self._fault = "episode ended"
