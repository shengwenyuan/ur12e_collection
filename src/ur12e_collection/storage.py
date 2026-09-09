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
from ur12e_collection import matching


class RecordingError(RuntimeError):
    """An episode cannot be accepted; any partial data is retained."""


def _sync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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
        crf: int = 20,
        match_config: matching.MatchConfig = matching.MatchConfig(),
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
        self.options = {
            "simulated": simulated,
            "capacity": capacity,
            "crf": crf,
            "matching": match_config,
        }
        self._queue = queue.Queue(maxsize=capacity)
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._status = {
            "state": "open",
            "error": None,
            "deadline": None,
            "report": None,
            "peak_queue": 0,
            "max_queue_delay_ns": 0,
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
            try:
                self._queue.put_nowait((operation, value, time.monotonic_ns()))
            except queue.Full as error:
                self._status.update(
                    state="aborted", error="recording queue overflow"
                )
                raise RecordingError("recording queue overflow") from error
            self._status["peak_queue"] = max(
                self._status["peak_queue"], self._queue.qsize()
            )

    def submit(self, group: matching.Match) -> None:
        """Submit image groups or rejection diagnostics without blocking."""
        self._submit("group" if group.accepted else "rejection", group)

    def submit_record(self, record, timestamp_ns: int) -> None:
        """Supply M10 data with its mapped Unix acquisition time."""
        self._submit("record", (record, timestamp_ns))

    def abort(self) -> None:
        """Prevent future commit; leave partial data for explicit inspection."""
        with self._lock:
            if self._status["state"] != "committed":
                self._status.update(state="aborted", error="operator aborted")

    def health(self) -> dict:
        """Expose asynchronous failure without waiting for file completion."""
        with self._lock:
            return {
                "state": self._status["state"],
                "error": self._status["error"],
                "queued": self._queue.qsize(),
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
                self._status["max_queue_delay_ns"] = max(
                    self._status["max_queue_delay_ns"],
                    time.monotonic_ns() - submitted_ns,
                )
            if operation == "record":
                writer.record(*value)
            else:
                getattr(writer, operation)(value)
        raise RecordingError("recording was aborted")

    def _commit(self, report: dict) -> None:
        _sync_directory(self.partial)
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
                _sync_directory(self.destination.parent)
            except OSError:
                self.destination.rename(self.partial)
                raise
            self._status.update(state="committed", report=report)

    def _run(self) -> None:
        started = time.monotonic()
        try:
            with (self.partial / "episode.mcap").open("xb") as stream:
                writer = archive.ArchiveWriter(
                    stream,
                    self.snapshot,
                    self.options["simulated"],
                    self.options["crf"],
                    config=self.options["matching"],
                )
                self._consume(writer)
                writer.finish()
                stream.flush()
                os.fsync(stream.fileno())
            verification = archive.verify_mcap(
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
                    {"state": "failed", "error": self._status["error"]},
                )
            except OSError:
                pass  # An unwritable filesystem cannot hold an error record.
        finally:
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
