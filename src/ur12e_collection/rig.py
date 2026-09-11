"""Bounded ownership of three persistent camera processes; no motion imports."""

import contextlib
import dataclasses
import math
import multiprocessing
import queue
import time
import uuid
from typing import Any

from ur12e_collection import (
    capture,
    contracts,
    realsense_source,
    station,
    synthetic,
    shared_frames,
)
from ur12e_collection import workers

QUEUE_CAPACITY = 4
STALE_NS = 2_000_000_000


def _synthetic_stream(config, role, clock_id, stop):
    yield synthetic.observations(config)[role]
    start = (math.floor(time.monotonic() * 30) + 1) / 30
    index = 0
    while not stop.is_set():
        if stop.wait(max(0, start + index / 30 - time.monotonic())):
            return
        yield synthetic.frame(
            role, index, clock_id, time.monotonic_ns(), time.time_ns()
        )
        index += 1


def _worker(config, role, clock_id, channels):
    workers.ignore_terminal_interrupt()
    frames, status, stop, backend, descriptor = channels
    slots = shared_frames.Slots.attach(descriptor) if descriptor else None
    source = (
        _synthetic_stream if backend == "synthetic" else realsense_source.stream
    )
    try:
        with contextlib.closing(source(config, role, clock_id, stop)) as stream:
            status.send(("ready", next(stream)))
            for frame in stream:
                try:
                    frames.put_nowait(slots.pack(frame) if slots else frame)
                except queue.Full as error:
                    raise RuntimeError(
                        f"camera IPC queue overflow: {role}"
                    ) from error
    except Exception as error:  # pylint: disable=broad-exception-caught
        with contextlib.suppress(BrokenPipeError, EOFError):
            status.send(("error", str(error)))
    finally:
        # Shutdown discards queued tails; normal operation drains continuously.
        frames.cancel_join_thread()
        frames.close()
        status.close()
        if slots is not None:
            slots.close()


@dataclasses.dataclass
class _Camera:
    process: Any
    frames: Any
    status: Any
    slots: shared_frames.Slots | None = None
    observed: dict | None = None
    last_receipt: int = 0
    stats: dict = dataclasses.field(
        default_factory=lambda: {
            "frames": 0,
            "color_gaps": 0,
            "depth_gaps": 0,
            "depth_repeats": 0,
            "max_delivery_ms": 0.0,
            "first_receipt_ns": None,
            "last_receipt_ns": None,
        }
    )
    previous: Any = None

    def observe(self, frame) -> None:
        """Count native observations independently of episode selection."""
        self.last_receipt = frame.color.time.received_monotonic_ns
        self.stats["first_receipt_ns"] = (
            self.stats["first_receipt_ns"] or self.last_receipt
        )
        self.stats["last_receipt_ns"] = self.last_receipt
        self.stats["frames"] += 1
        self.stats["max_delivery_ms"] = max(
            self.stats["max_delivery_ms"],
            (time.monotonic_ns() - self.last_receipt) / 1e6,
        )
        if self.previous is not None:
            color = frame.color.sequence - self.previous.color.sequence
            depth = frame.depth.sequence - self.previous.depth.sequence
            if (
                color <= 0
                or depth < 0
                or frame.timestamp_ns <= self.previous.timestamp_ns
            ):
                raise RuntimeError("camera counters restarted")
            self.stats["color_gaps"] += max(0, color - 1)
            self.stats["depth_gaps"] += max(0, depth - 1)
            self.stats["depth_repeats"] += depth == 0
        self.previous = dataclasses.replace(frame, payload=None)


class Rig:
    """Own one rig generation; a fault requires an explicit new run."""

    def __init__(
        self,
        config: dict,
        backend: str,
        *,
        queue_capacity: int = QUEUE_CAPACITY,
        shared_slots: dict | None = None,
        stop=None,
    ):
        station.validate(config, cameras_ready=True)
        if backend not in ("hardware", "synthetic"):
            raise ValueError("an explicit camera backend is required")
        if backend == "synthetic" and config != synthetic.configuration():
            raise ValueError(
                "synthetic sources require synthetic configuration"
            )
        if (
            not isinstance(queue_capacity, int)
            or isinstance(queue_capacity, bool)
            or not 1 <= queue_capacity <= 16
        ):
            raise ValueError("camera queue capacity must be between 1 and 16")
        self._queue_capacity = queue_capacity
        self._shared_slots = shared_slots or {}
        if self._shared_slots and set(self._shared_slots) != set(
            contracts.CAMERA_ROLES
        ):
            raise ValueError("shared slots require all three camera roles")
        self.config = config
        self.backend = backend
        self.clock_id = str(uuid.uuid4())
        self._context = multiprocessing.get_context("spawn")
        self._stop = stop if stop is not None else self._context.Event()
        self._cameras: dict[str, _Camera] = {}
        self._epoch_offset = time.time_ns() - time.monotonic_ns()
        self._closed = False

    @property
    def observations(self) -> dict:
        """Return observed camera facts only after every worker is ready."""
        if len(self._cameras) != 3 or any(
            c.observed is None for c in self._cameras.values()
        ):
            raise RuntimeError("rig is not ready")
        return {role: camera.observed for role, camera in self._cameras.items()}

    def start(self, timeout: float = 30) -> None:
        """Start once, draining early cameras while awaiting all readiness."""
        if self._cameras or self._closed:
            raise RuntimeError("rig can only start once")
        try:
            for role in contracts.CAMERA_ROLES:
                parent, child = self._context.Pipe(duplex=False)
                frames = self._context.Queue(maxsize=self._queue_capacity)
                slots = (
                    shared_frames.Slots.attach(self._shared_slots[role])
                    if self._shared_slots
                    else None
                )
                process = self._context.Process(
                    target=_worker,
                    args=(
                        self.config,
                        role,
                        self.clock_id,
                        (
                            frames,
                            child,
                            self._stop,
                            self.backend,
                            slots.descriptor() if slots else None,
                        ),
                    ),
                    daemon=True,
                )
                try:
                    process.start()
                except BaseException:
                    parent.close()
                    child.close()
                    frames.close()
                    frames.cancel_join_thread()
                    if slots is not None:
                        slots.close()
                    raise
                child.close()
                self._cameras[role] = _Camera(process, frames, parent, slots)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self.read()
                if all(c.observed is not None for c in self._cameras.values()):
                    return
            raise TimeoutError("camera startup exceeded its deadline")
        except BaseException:
            self.close()
            raise

    def read(self, timeout: float | None = None) -> list:
        """Drain bounded queues fairly and check source/clock health."""
        if self._closed:
            raise RuntimeError("rig is closed")
        offset = time.time_ns() - time.monotonic_ns()
        if abs(offset - self._epoch_offset) > 100_000_000:
            raise RuntimeError("host wall clock stepped during camera run")
        result = []
        for role, camera in self._cameras.items():
            while camera.status.poll():
                try:
                    kind, value = camera.status.recv()
                except EOFError as error:
                    raise RuntimeError(
                        f"camera worker exited: {role}"
                    ) from error
                if kind == "error":
                    raise RuntimeError(value)
                camera.observed = value
                camera.last_receipt = time.monotonic_ns()
            if not camera.process.is_alive():
                raise RuntimeError(f"camera worker exited: {role}")
            for _ in range(self._queue_capacity):
                try:
                    frame = camera.frames.get_nowait()
                except queue.Empty:
                    break
                if camera.slots is not None:
                    frame = camera.slots.unpack(frame)
                camera.observe(frame)
                result.append(frame)
            if camera.observed is not None and (
                time.monotonic_ns() - camera.last_receipt > STALE_NS
            ):
                raise TimeoutError(f"camera stream stalled: {role}")
        if not result:
            self._stop.wait(
                capture.resolve(self.config)["empty_poll_ns"] / 1e9
                if timeout is None
                else timeout
            )
        return result

    def statistics(self) -> dict:
        """Report all observed frames, including periods between episodes."""
        result = {}
        for role, camera in self._cameras.items():
            stats = dict(camera.stats)
            duration = (
                (stats["last_receipt_ns"] or 0)
                - (stats["first_receipt_ns"] or 0)
            ) / 1e9
            stats["received_fps"] = (
                (stats["frames"] - 1) / duration if duration > 0 else None
            )
            result[role] = stats
        return result

    def request_stop(self) -> None:
        """Signal all camera workers before waiting for any source owner."""
        self._stop.set()

    def close(self) -> None:
        """Request cooperative stop, then bound native process cleanup."""
        if self._closed:
            return
        self._closed = True
        self.request_stop()
        errors = []
        for camera in self._cameras.values():
            workers.stop(camera.process)
            if camera.slots is not None:
                camera.slots.close()
            while camera.status.poll():
                try:
                    kind, value = camera.status.recv()
                except EOFError:
                    break
                if kind == "error":
                    errors.append(value)
            if camera.process.exitcode != 0:
                errors.append(
                    f"camera required forced cleanup: {camera.process.exitcode}"
                )
            camera.frames.close()
            camera.frames.cancel_join_thread()
            camera.status.close()
        if errors:
            raise RuntimeError("; ".join(errors))
