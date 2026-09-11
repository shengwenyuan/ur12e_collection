"""Bounded asynchronous ownership and atomic completion of local episodes."""

import importlib.metadata
import json
import os
import pathlib
import queue
import threading
import time

import av

# PyAV defines this exception in Cython; decode failures exercise the boundary.
from av.error import FFmpegError  # pylint: disable=no-name-in-module
from mcap.exceptions import McapError

from ur12e_collection import archive
from ur12e_collection import matching, filesystem

FEEDBACK_CAPACITY = 64


class RecordingError(RuntimeError):
    """An episode cannot be accepted; any partial data is retained."""


def _json_file(path: pathlib.Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(archive.json_text(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class EpisodeWriter:
    """Own a bounded queue; successful submission transfers image ownership."""

    # The lifecycle lock is separate from queue/event synchronization.
    # Explicit keyword controls keep queue, codec and matching choices distinct.
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        destination: pathlib.Path,
        snapshot: dict,
        *,
        simulated: bool,
        capacity: int = 4,
        feedback_capacity: int = FEEDBACK_CAPACITY,
        crf: int = 20,
        match_config: matching.MatchConfig = matching.MatchConfig(),
        verify=None,
    ):
        if (
            not isinstance(simulated, bool)
            or (not isinstance(capacity, int) or isinstance(capacity, bool))
            or capacity < 1
        ):
            raise ValueError(
                "explicit synthetic provenance and positive capacity required"
            )
        if (
            not isinstance(feedback_capacity, int)
            or isinstance(feedback_capacity, bool)
            or not 1 <= feedback_capacity <= 256
        ):
            raise ValueError("feedback capacity must be between 1 and 256")
        if (
            not isinstance(crf, int) or isinstance(crf, bool)
        ) or not 0 <= crf <= 51:
            raise ValueError("CRF must be from 0 to 51")
        destination = pathlib.Path(destination).absolute()
        if destination.name.endswith((".partial", ".lock")):
            raise ValueError("episode name must not use a reserved suffix")
        self.destination = destination
        self.partial = destination.with_name(destination.name + ".partial")
        self.snapshot = archive.snapshot_copy(snapshot)
        if not isinstance(match_config, matching.MatchConfig):
            raise ValueError("recording requires a validated MatchConfig")
        archive.GroupValidator(self.snapshot, simulated, match_config)
        self.options = {
            "simulated": simulated,
            "capacity": capacity,
            "feedback_capacity": feedback_capacity,
            "crf": crf,
            "matching": match_config,
            "verify": verify,
        }
        self._queue = queue.Queue(maxsize=capacity + feedback_capacity)
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._status = {
            "state": "open",
            "initialized": False,
            "error": None,
            "deadline": None,
            "report": None,
            "peak_queue": 0,
            "peak_feedback_queue": 0,
            "queued": 0,
            "queued_feedback": 0,
            "max_queue_delay_ns": 0,
            "operations": {},
        }
        self._reservation = destination.with_name(destination.name + ".lock")
        self._reserve()
        try:
            threading.Thread(
                target=self._run, name="episode-writer", daemon=True
            ).start()
        except BaseException:
            self._reservation.unlink()
            raise

    def _reserve(self) -> None:
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        with self._reservation.open("x", encoding="utf-8"):
            pass
        try:
            if self.destination.exists() or self.destination.is_symlink():
                raise FileExistsError(self.destination)
            self.partial.mkdir()
        except BaseException:
            self._reservation.unlink()
            raise

    def _submit(self, operation: str, value) -> None:
        with self._lock:
            if self._status["state"] != "open":
                raise RecordingError(
                    self._status["error"] or "writer is closed"
                )
            is_feedback = operation == "records"
            key = "queued_feedback" if is_feedback else "queued"
            peak = "peak_feedback_queue" if is_feedback else "peak_queue"
            count = len(value) if is_feedback else 1
            capacity = (
                self.options["feedback_capacity"]
                if is_feedback
                else self.options["capacity"]
            )
            if self._status[key] + count > capacity:
                error = (
                    f"recording queue overflow: {key}="
                    f"{self._status[key]} + {count} > {capacity}"
                )
                self._status.update(state="aborted", error=error)
                raise RecordingError(error)
            self._queue.put_nowait((operation, value, time.monotonic_ns()))
            self._status[key] += count
            self._status[peak] = max(self._status[peak], self._status[key])

    def submit(self, group: matching.Match) -> None:
        """Submit image groups or rejection diagnostics without blocking."""
        self._submit("group" if group.accepted else "rejection", group)

    def submit_record(self, record, timestamp_ns: int) -> None:
        """Supply M10 data with its mapped Unix acquisition time."""
        self._submit("record", (record, timestamp_ns))

    def submit_records(self, records: tuple) -> None:
        """Batch at most one bounded drain from each feedback source."""
        if not isinstance(records, tuple) or not 1 <= len(records) <= 64:
            raise ValueError("feedback batch must contain 1-64 records")
        self._submit("records", records)

    def abort(self) -> None:
        """Prevent future commit; leave partial data for explicit inspection."""
        with self._lock:
            if self._status["state"] != "committed":
                self._status.update(
                    state="aborted",
                    error=self._status["error"] or "operator aborted",
                )

    def health(self) -> dict:
        """Expose asynchronous failure without waiting for file completion."""
        with self._lock:
            return {
                "state": self._status["state"],
                "initialized": self._status["initialized"],
                "error": self._status["error"],
                "queued": self._status["queued"],
                "queued_feedback": self._status["queued_feedback"],
                "max_queue_delay_ms": self._status["max_queue_delay_ns"] / 1e6,
                "operations": {
                    key: dict(value)
                    for key, value in self._status["operations"].items()
                },
            }

    def finish(self, timeout: float = 30) -> dict:
        """Flush and verify within a bound; timeout forbids later commit."""
        if not 0 < timeout <= 300:
            raise ValueError("completion timeout must be in (0, 300] seconds")
        deadline = time.monotonic() + timeout
        with self._lock:
            state = self._status["state"]
            if state == "committed":
                return dict(self._status["report"])
            if state != "open":
                raise RecordingError(
                    self._status["error"] or "writer already closing"
                )
            self._status.update(state="closing", deadline=deadline)
        try:
            self._queue.put(None, timeout=max(0, deadline - time.monotonic()))
        except queue.Full:
            pass
        self._done.wait(max(0, deadline - time.monotonic()))
        with self._lock:
            if self._status["state"] == "committed":
                return dict(self._status["report"])
            self._status.update(
                state="aborted",
                error=self._status["error"] or "completion timed out",
            )
            raise RecordingError(self._status["error"])

    def wait_closed(self, timeout: float = 5) -> bool:
        """Wait for cleanup after abort/failure without permitting commit."""
        return self._done.wait(timeout)

    def _active(self) -> bool:
        with self._lock:
            return self._status["state"] in ("open", "closing")

    def _consume(self, writer: archive.ArchiveWriter) -> None:
        while self._active():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                return
            operation, value, submitted_ns = item
            with self._lock:
                key = "queued_feedback" if operation == "records" else "queued"
                self._status[key] -= len(value) if operation == "records" else 1
                self._status["max_queue_delay_ns"] = max(
                    self._status["max_queue_delay_ns"],
                    time.monotonic_ns() - submitted_ns,
                )
            started_ns = time.monotonic_ns()
            if operation == "records":
                for record in value:
                    writer.record(*record)
            elif operation == "record":
                writer.record(*value)
            else:
                getattr(writer, operation)(value)
            elapsed_ms = (time.monotonic_ns() - started_ns) / 1e6
            with self._lock:
                stats = self._status["operations"].setdefault(
                    operation, {"count": 0, "total_ms": 0.0, "max_ms": 0.0}
                )
                stats["count"] += 1
                stats["total_ms"] += elapsed_ms
                stats["max_ms"] = max(stats["max_ms"], elapsed_ms)
        raise RecordingError("recording was aborted")

    def _commit(self, report: dict) -> None:
        filesystem.sync(self.partial)
        with self._lock:
            deadline = self._status["deadline"]
            if (
                self._status["state"] != "closing"
                or deadline is None
                or time.monotonic() >= deadline
            ):
                raise RecordingError("aborted or expired completion")
            if self.destination.exists() or self.destination.is_symlink():
                raise FileExistsError(self.destination)
            self.partial.rename(self.destination)
            try:
                filesystem.sync(self.destination.parent)
            except OSError:
                self.destination.rename(self.partial)
                raise
            self._status.update(state="committed", report=report)

    def _run(self) -> None:
        started = time.monotonic()
        writer = None
        try:
            with (self.partial / "episode.mcap").open("xb") as stream:
                writer = archive.ArchiveWriter(
                    stream,
                    self.snapshot,
                    self.options["simulated"],
                    self.options["crf"],
                    config=self.options["matching"],
                )
                with self._lock:
                    self._status["initialized"] = True
                self._consume(writer)
                writer.finish()
                stream.flush()
                os.fsync(stream.fileno())
            verification = (self.options["verify"] or archive.verify_mcap)(
                self.partial / "episode.mcap",
                self.snapshot,
                self.options["simulated"],
                self.options["matching"],
            )
            if verification["counts"] != dict(writer.counts):
                raise RecordingError(
                    "stored message counts differ from submissions"
                )
            report = {
                **writer.validator.context(),
                "state": "complete",
                "verification": verification,
                "codecs": {
                    "rgb": "h264",
                    "crf": self.options["crf"],
                    "preset": "veryfast",
                    "pixel_format": "yuv420p",
                    "gop": 30,
                    "b_frames": 0,
                    "depth": "uint16_png",
                    "png_level": 1,
                    "chunk_compression": "none",
                },
                "payload_bytes": dict(writer.payload_bytes),
                "encode_total_ms": {
                    k: v / 1e6 for k, v in writer.encode_ns.items()
                },
                "encode_max_ms": {
                    k: v / 1e6 for k, v in writer.max_encode_ns.items()
                },
                "max_queue_delay_ms": self._status["max_queue_delay_ns"] / 1e6,
                "queue_capacity": self.options["capacity"],
                "peak_queue": self._status["peak_queue"],
                "feedback_queue_capacity": self.options["feedback_capacity"],
                "write_operations": self._status["operations"],
                "peak_feedback_queue": self._status["peak_feedback_queue"],
                "elapsed_s": time.monotonic() - started,
                "libraries": {
                    name: importlib.metadata.version(name)
                    for name in (
                        "av",
                        "mcap",
                        "mcap-ros2-support",
                        "opencv-contrib-python-headless",
                    )
                },
                "linked_av_libraries": av.library_versions,
            }
            _json_file(self.partial / "metadata.json", report)
            self._commit(report)
        except Exception as error:  # pylint: disable=broad-exception-caught
            # Convert all worker exceptions to a failed episode for its owner.
            with self._lock:
                self._status.update(
                    state="failed", error=self._status["error"] or str(error)
                )
            try:
                _json_file(
                    self.partial / "failure.json",
                    self.health(),
                )
            except OSError:
                pass  # An unwritable filesystem cannot hold an error record.
        finally:
            if writer is not None:
                writer.close()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            try:
                self._reservation.unlink(missing_ok=True)
            finally:
                self._done.set()


def verify_episode(path: pathlib.Path) -> dict:
    """Validate a completed episode without trusting its stored success flag."""
    path = pathlib.Path(path)
    if path.name.endswith(".partial"):
        raise ValueError("partial directories are not completed episodes")
    try:
        metadata = json.loads(
            (path / "metadata.json").read_text(encoding="utf-8")
        )
        if metadata["schema_version"] != 1 or metadata["state"] != "complete":
            raise ValueError(
                "episode metadata is not a supported completed record"
            )
        if metadata["time_semantics"] != archive.TIME_SEMANTICS:
            raise ValueError("unsupported episode time semantics")
        result = archive.verify_mcap(
            path / "episode.mcap",
            metadata["snapshot"],
            metadata["simulated"],
            matching.MatchConfig(**metadata["matching"]),
        )
        if result != metadata["verification"]:
            raise ValueError("episode verification differs from metadata")
        return result
    except (McapError, FFmpegError, KeyError, EOFError, TypeError) as error:
        raise ValueError(f"episode decoding failed: {error}") from error
