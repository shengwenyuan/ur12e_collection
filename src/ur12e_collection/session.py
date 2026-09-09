"""Camera-episode lifecycle shared by shadow and future session ownership."""

import concurrent.futures
import pathlib
import threading

from ur12e_collection import matching, snapshots, storage


class Session:
    """Single submission owner; finalization never pauses camera draining."""

    def __init__(self, snapshot: dict, config: matching.MatchConfig):
        self.snapshot = snapshots.copy(snapshot)
        self.config = config
        self.state = "idle"
        self.writer = None
        self.matcher = None
        self.boundaries = {}
        self._completion = None

    def start(self, destination: pathlib.Path, now_ns: int) -> None:
        """Open an independent episode at an explicit host receipt boundary."""
        if self.state != "idle":
            raise RuntimeError("episode start requires idle state")
        self.writer = storage.EpisodeWriter(
            destination,
            self.snapshot,
            simulated=self.snapshot["simulated"],
            match_config=self.config,
        )
        self.matcher = matching.Matcher(self.snapshot["clock_id"], self.config)
        self.boundaries = {"start_receipt_ns": now_ns}
        self.state = "recording"

    def submit(self, frame: matching.Frame, now_ns: int) -> None:
        """Record current-episode frames; drain but ignore other periods."""
        if self.state != "recording":
            return
        if (
            frame.color.time.received_monotonic_ns
            < self.boundaries["start_receipt_ns"]
        ):
            return
        try:
            for result in self.matcher.push(frame, now_ns):
                self.writer.submit(result)
        except Exception:
            self.abort()
            raise

    def advance(self, now_ns: int) -> None:
        """Resolve bounded matching waits when a source is temporarily quiet."""
        if self.state == "recording":
            try:
                for result in self.matcher.advance(now_ns):
                    self.writer.submit(result)
            except Exception:
                self.abort()
                raise

    def stop(self, now_ns: int) -> None:
        """Close the sample boundary and finalize asynchronously."""
        if self.state != "recording":
            raise RuntimeError("episode stop requires recording state")
        try:
            for result in self.matcher.finish(now_ns):
                self.writer.submit(result)
            self.boundaries["stop_receipt_ns"] = now_ns
            self._completion = concurrent.futures.Future()
            self.state = "finalizing"
            threading.Thread(
                target=self._finalize, daemon=True, name="episode-finalizer"
            ).start()
        except Exception:
            self.abort()
            raise

    def _finalize(self) -> None:
        try:
            self._completion.set_result(self.writer.finish())
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._completion.set_exception(error)

    def poll(self) -> dict | None:
        """Surface writer failures or return one completed report."""
        if self.state not in ("recording", "finalizing"):
            return None
        if self.writer.health()["state"] in ("aborted", "failed"):
            error = self.writer.health()["error"]
            self.abort()
            raise storage.RecordingError(error)
        if self.state != "finalizing" or not self._completion.done():
            return None
        try:
            report = self._completion.result()
        except Exception:
            self.abort()
            raise
        result = {
            "episode": self.writer.destination.name,
            **self.boundaries,
            "matching": dict(self.matcher.counters),
            "recording": report,
        }
        self.writer = self.matcher = self._completion = None
        self.state = "idle"
        return result

    def abort(self) -> None:
        """Revoke completion without blocking the acquisition owner."""
        if self.writer is not None:
            self.writer.abort()
        self.state = "failed"

    def close(self) -> None:
        """Abort active work and bound cleanup outside the acquisition loop."""
        if self.writer is not None:
            self.writer.abort()
            if not self.writer.wait_closed():
                raise TimeoutError("episode worker did not finish cleanup")
        self.state = "closed"
