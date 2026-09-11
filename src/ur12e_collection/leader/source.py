"""Persistent read-only sampling, with bounded independent consumers."""

import collections
import dataclasses
import threading
import time
import uuid

from ur12e_collection.leader import bus, episode, probe

READ_HZ = 120
FRESH_NS = 100_000_000
HEALTH_NS = 2_000_000_000


@dataclasses.dataclass(frozen=True)
class Motion:
    """One complete acquisition; velocity stays in DYNAMIXEL raw units."""

    sample: episode.Sample
    velocity_raw: tuple[int, ...]


@dataclasses.dataclass(frozen=True)
class View:
    """Detached recent motion and independently timestamped health."""

    recent: tuple[Motion, ...]
    health: bus.Block


class Mailbox:
    """Latest control view and loss-intolerant bounded recording channel."""

    def __init__(self, capacity=120):
        if (
            not isinstance(capacity, int)
            or isinstance(capacity, bool)
            or capacity < 1
        ):
            raise ValueError("positive recording capacity required")
        self._capacity = capacity
        self._lock = threading.Lock()
        self._recent = collections.deque(maxlen=4)
        self._pending = collections.deque()
        self._health = None
        self._fault = None
        self.peak = 0

    def fail(self, reason: str) -> None:
        """Keep the first fault; recovery requires a new source instance."""
        with self._lock:
            self._fault = self._fault or reason

    def _check(self):
        if self._fault:
            raise bus.ReadError(self._fault)

    def health(self, block: bus.Block) -> None:
        """Health errors invalidate control before publishing another sample."""
        with self._lock:
            self._check()
            if any(block.errors) or any(block.integers(70, 1)):
                self._fault = "leader health error"
                self._check()
            self._health = block

    def publish(self, motion: Motion) -> None:
        """Latch chronology faults and queue overflow; never drop silently."""
        with self._lock:
            self._check()
            if self._recent:
                previous = self._recent[-1].sample
                current = motion.sample
                if (
                    current.epoch != previous.epoch
                    or current.sequence != previous.sequence + 1
                    or current.start_ns < previous.end_ns
                    or not 0 < current.start_ns - previous.start_ns <= FRESH_NS
                ):
                    self._fault = "leader stream discontinuity"
            if len(self._pending) >= self._capacity:
                self._fault = self._fault or "leader recording queue overflow"
            self._check()
            self._recent.append(motion)
            self._pending.append(motion)
            self.peak = max(self.peak, len(self._pending))

    def view(self, now_ns: int | None = None) -> View:
        """Never refresh cached timestamps; stale or closed sources fail."""
        with self._lock:
            self._check()
            if not self._recent or self._health is None:
                raise bus.ReadError("leader source not ready")
            now_ns = time.monotonic_ns() if now_ns is None else now_ns
            sample = self._recent[-1].sample
            if not (
                sample.end_ns <= now_ns <= sample.start_ns + FRESH_NS
                and self._health.end_ns
                <= now_ns
                <= self._health.start_ns + HEALTH_NS
            ):
                motion_age = (now_ns - sample.start_ns) / 1e6
                health_age = (now_ns - self._health.start_ns) / 1e6
                self._fault = (
                    "stale leader motion or health: "
                    f"motion={motion_age:.2f} ms, "
                    f"health={health_age:.2f} ms"
                )
                self._check()
            return View(tuple(self._recent), self._health)

    def drain(self) -> tuple[Motion, ...]:
        """Retain already acquired evidence even after a latched failure."""
        with self._lock:
            values = tuple(self._pending)
            self._pending.clear()
            return values


class Reader:
    """One worker owns the serial connection from open through close."""

    def __init__(self, device: str, baudrate: int, *, capacity=120):
        self.mailbox = Mailbox(capacity)
        self.inventory = {}
        self.traffic = {}
        self.epoch = uuid.uuid4().hex
        self._connection = (device, baudrate)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="gello-read")

    def start(self) -> None:
        """Open once and await first trustworthy feedback, without writes."""
        self._thread.start()
        if not self._ready.wait(10):
            self.close()
            raise bus.ReadError("leader startup timed out")
        try:
            self.mailbox.view()
        except bus.ReadError:
            self.close()
            raise

    def _run(self):
        connection = None
        try:
            with bus.ReadBus(*self._connection) as connection:
                self.inventory = probe.inventory(connection)
                if any(
                    row["status_errors"] != [0] or row["hardware_error"]
                    for row in self.inventory.values()
                ):
                    raise bus.ReadError("leader inventory reports a fault")
                if any(row["firmware"] < 45 for row in self.inventory.values()):
                    raise bus.ReadError(
                        "fast sync requires XL430 firmware >=45"
                    )
                self._sample(connection)
        # Any worker failure must reach both consumers, including SDK defects.
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.mailbox.fail(f"{type(error).__name__}: {error}")
        finally:
            if connection is not None:
                self.traffic = connection.traffic()
            self._ready.set()

    def _sample(self, connection):
        health = connection.sync(64, 7, fast=True)
        self.mailbox.health(health)
        health_due = health.end_ns + 1_000_000_000
        sequence = 0
        period = round(1e9 / READ_HZ)
        deadline = time.monotonic_ns()
        while not self._stop.is_set():
            block = connection.sync(128, 8, fast=True)
            sample = episode.Sample(
                self.epoch,
                sequence,
                block.start_ns,
                block.end_ns,
                block.integers(132, 4, signed=True),
                block.errors,
            )
            self.mailbox.publish(
                Motion(sample, block.integers(128, 4, signed=True))
            )
            sequence += 1
            self._ready.set()
            # Health work shares the idle budget, not the next motion period.
            if time.monotonic_ns() >= health_due:
                health = connection.sync(64, 7, fast=True)
                self.mailbox.health(health)
                health_due = health.end_ns + 1_000_000_000
            deadline = next_deadline(deadline, time.monotonic_ns(), period)
            self._stop.wait(max(0, (deadline - time.monotonic_ns()) / 1e9))

    def close(self) -> None:
        """Invalidate consumers before waiting for the serial owner to close."""
        self.mailbox.fail("leader source closed")
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join(10)
            if self._thread.is_alive():
                raise bus.ReadError("serial owner did not exit")


def next_deadline(previous: int, now: int, period: int) -> int:
    """Preserve phase and skip expired slots without catch-up bursts."""
    deadline = previous + period
    if deadline <= now:
        deadline += ((now - deadline) // period + 1) * period
    return deadline
