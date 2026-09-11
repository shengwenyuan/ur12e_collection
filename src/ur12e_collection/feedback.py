"""Bounded supervision of persistent, read-only UR and Hand-E feedback."""

import contextlib
import dataclasses
import multiprocessing
import queue
import time
from typing import Any

from ur12e_collection import feedback_source, workers

DEVICES = ("ur", "hande")
QUEUE_CAPACITY = 32
STALE_NS = 500_000_000


def _worker(device, config, backend, channels):
    samples, status, stop = channels
    stream = (
        feedback_source.synthetic_stream(device, stop)
        if backend == "synthetic"
        else {
            "ur": feedback_source.ur_stream,
            "hande": feedback_source.hande_stream,
        }[device](config, stop)
    )
    try:
        with contextlib.closing(stream):
            status.send(("ready", next(stream)))
            for sample in stream:
                samples.put_nowait(sample)
    except Exception as error:  # pylint: disable=broad-exception-caught
        status.send(("error", f"{device}: {type(error).__name__}: {error}"))
    finally:
        samples.cancel_join_thread()
        samples.close()
        status.close()


@dataclasses.dataclass
class _Device:
    process: Any
    samples: Any
    status: Any
    identity: dict | None = None
    last_receipt: int = 0
    previous: Any = None
    count: int = 0

    def observe(self, sample) -> None:
        """Never count repeated controller packets as fresh observations."""
        current = sample.provenance
        if (
            self.identity is None
            or current.source_id != self.identity["source_id"]
        ):
            raise ValueError("feedback identity changed")
        if self.previous is not None:
            previous = self.previous.provenance
            if (
                current.sequence != previous.sequence + 1
                or current.time.received_monotonic_ns
                <= previous.time.received_monotonic_ns
            ):
                raise ValueError(
                    "feedback receipt sequence restarted or skipped"
                )
            if current.time.source_ns is not None:
                if current.time.source_ns <= previous.time.source_ns:
                    raise ValueError(
                        "UR controller timestamp repeated or restarted"
                    )
        self.previous = sample
        self.last_receipt = current.time.received_monotonic_ns
        self.count += 1


class Feedback:
    """Readiness and failures are explicit; reconnect requires a new run."""

    def __init__(self, config: dict, backend: str):
        if backend not in ("hardware", "synthetic"):
            raise ValueError("feedback requires an explicit backend")
        if backend == "hardware" and not (
            config["ur"]["host"]
            and config["ur"]["serial"]
            and config["hande"]["host"]
            and config["hande"]["port"]
        ):
            raise ValueError(
                "feedback requires explicit UR/Hand-E endpoints and UR serial"
            )
        self.config = config
        self.backend = backend
        self._context = multiprocessing.get_context("spawn")
        self._stop = workers.Cancellation(self._context)
        self._devices = {}
        self._closed = False

    @property
    def observations(self) -> dict:
        """Source facts accompany every episode snapshot."""
        if len(self._devices) != 2 or any(
            d.identity is None or not d.count for d in self._devices.values()
        ):
            raise RuntimeError("feedback not ready")
        return {name: d.identity for name, d in self._devices.items()}

    def start(self, drain, timeout: float = 15) -> None:
        """Wait for both sources while draining live cameras."""
        if self._devices or self._closed:
            raise RuntimeError("feedback can only start once")
        try:
            for name in DEVICES:
                parent, child = self._context.Pipe(duplex=False)
                samples = self._context.Queue(maxsize=QUEUE_CAPACITY)
                process = self._context.Process(
                    target=_worker,
                    args=(
                        name,
                        self.config[name],
                        self.backend,
                        (samples, child, self._stop),
                    ),
                    daemon=True,
                )
                try:
                    process.start()
                except BaseException:
                    for handle in (parent, child, samples):
                        handle.close()
                    raise
                child.close()
                self._devices[name] = _Device(process, samples, parent)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                drain()
                self.read()
                if all(d.identity and d.count for d in self._devices.values()):
                    return
                self._stop.wait(0.001)
            raise TimeoutError("feedback startup timed out")
        except BaseException:
            self.close()
            raise

    def read(self) -> list:
        """Drain without blocking; fail on stalls or overflow."""
        if self._closed:
            raise RuntimeError("feedback closed")
        result = []
        for name, device in self._devices.items():
            while device.status.poll():
                try:
                    kind, value = device.status.recv()
                except EOFError as error:
                    raise RuntimeError(
                        f"feedback worker exited: {name}"
                    ) from error
                if kind == "error":
                    raise RuntimeError(value)
                device.identity = value
                device.last_receipt = time.monotonic_ns()
            if not device.process.is_alive():
                raise RuntimeError(f"feedback worker exited: {name}")
            for _ in range(QUEUE_CAPACITY):
                try:
                    sample = device.samples.get_nowait()
                except queue.Empty:
                    break
                device.observe(sample)
                result.append(sample)
            if (
                device.identity
                and time.monotonic_ns() - device.last_receipt > STALE_NS
            ):
                raise TimeoutError(f"stale feedback: {name}")
        return result

    def statistics(self) -> dict:
        """Count observations during recording and between episodes."""
        return {
            name: {"samples": d.count, "last_receipt_ns": d.last_receipt}
            for name, d in self._devices.items()
        }

    def request_stop(self) -> None:
        """Signal local readers without waiting or commanding either device."""
        self._stop.set()

    def close(self) -> None:
        """Stop only local readers; no device-side stop/hold command exists."""
        if self._closed:
            return
        errors = []
        self.request_stop()
        self._closed = True
        for name, device in self._devices.items():
            workers.stop(device.process, grace_s=2)
            while device.status.poll():
                try:
                    kind, value = device.status.recv()
                except EOFError:
                    break
                if kind == "error":
                    errors.append(value)
            if device.process.exitcode != 0:
                errors.append(f"feedback required forced cleanup: {name}")
            device.samples.close()
            device.samples.cancel_join_thread()
            device.status.close()
        if errors:
            raise RuntimeError("; ".join(errors))
