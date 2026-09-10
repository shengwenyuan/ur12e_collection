"""Camera-episode lifecycle shared by shadow and future session ownership."""

import concurrent.futures
import pathlib
import threading

from ur12e_collection import matching, snapshots, storage


class Session:
    """Single submission owner; finalization never pauses camera draining."""

    def __init__(
        self, snapshot: dict, config: matching.MatchConfig, *, verify=None
    ):
        self.snapshot = snapshots.copy(snapshot)
        self.config = config
        self.verify = verify
        self.state = "idle"
        self.writer = None
        self.matcher = None
        self.boundaries = {}
        self._completion = None

    @classmethod
    def from_snapshot(cls, snapshot: dict, *, verify=None):
        """Derive runtime matching from the frozen station/capture context."""
        return cls(
            snapshot,
            matching.MatchConfig(
                max_skew_ns=snapshot["station"]["max_skew_ns"],
                wait_ns=snapshot["capture"]["wait_ns"],
            ),
            verify=verify,
        )

    def start(self, destination: pathlib.Path, now_ns: int) -> None:
        """Prepare and start at the caller's explicit receipt boundary."""
        self.prepare(destination)
        self.begin(now_ns)

    def prepare(self, destination: pathlib.Path) -> None:
        """Create the writer before the control owner permits following."""
        if self.state != "idle":
            raise RuntimeError("episode start requires idle state")
        self.writer = storage.EpisodeWriter(
            destination,
            self.snapshot,
            simulated=self.snapshot["simulated"],
            match_config=self.config,
            capacity=self.snapshot.get("control", {}).get(
                "writer_queue_capacity", 4
            ),
            verify=self.verify,
        )
        self.matcher = matching.Matcher(self.snapshot["clock_id"], self.config)
        self.boundaries = {}
        self.state = "prepared"

    def begin(self, now_ns: int) -> None:
        """Commit the shared start boundary only after preparation succeeds."""
        if self.state != "prepared":
            raise RuntimeError("episode begin requires prepared state")
        self.boundaries = {"start_receipt_ns": now_ns}
        self.state = "recording"

    def submit(self, frame: matching.Frame, now_ns: int) -> None:
        """Record current-episode frames; drain but ignore other periods."""
        if not self._recordable(frame.color.time.received_monotonic_ns):
            return
        try:
            for result in self.matcher.push(frame, now_ns):
                self.writer.submit(result)
        except Exception:
            self.abort()
            raise

    def _recordable(self, receipt: int) -> bool:
        if (
            self.state == "finalizing"
            and self.boundaries["start_receipt_ns"]
            <= receipt
            < self.boundaries["stop_receipt_ns"]
        ):
            self.abort()
            raise storage.RecordingError("frame arrived after capture drain")
        return (
            self.state == "recording"
            and receipt >= self.boundaries["start_receipt_ns"]
        )

    def submit_feedback(self, samples: list) -> None:
        """Keep independent feedback clocks and the same receipt window."""
        records = []
        context = self.snapshot.get("control", self.snapshot.get("feedback"))
        offset = context["monotonic_to_unix_ns"]
        try:
            for sample in samples:
                receipt = sample.provenance.time.received_monotonic_ns
                if self._recordable(receipt):
                    records.append((sample, receipt + offset))
            if records:
                self.writer.submit_records(tuple(records))
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

    def stop(self, now_ns: int, *, cutoff_ns: int | None = None) -> None:
        """Finalize after draining; the caller enforces any earlier cutoff."""
        if self.state != "recording":
            raise RuntimeError("episode stop requires recording state")
        cutoff = now_ns if cutoff_ns is None else cutoff_ns
        if not self.boundaries["start_receipt_ns"] <= cutoff <= now_ns:
            raise ValueError("capture cutoff must be inside the session")
        try:
            for result in self.matcher.finish(now_ns):
                self.writer.submit(result)
            self.boundaries["stop_receipt_ns"] = cutoff
            self.boundaries["finalize_requested_ns"] = now_ns
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
        if self.state not in ("prepared", "recording", "finalizing"):
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
