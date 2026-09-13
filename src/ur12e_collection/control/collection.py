"""Persistent recording coordination around the existing teleop motion owner."""

import dataclasses
import pathlib
import time

from ur12e_collection import filesystem
from ur12e_collection.control import model, records
from ur12e_collection.control.session import write_outcome


@dataclasses.dataclass
class Episode:
    """State belonging to one prepared or recorded episode."""

    path: pathlib.Path
    records: records.Records
    start: int = 0
    cutoff: int = 0
    settled_ns: int = 0
    last_target: int = 0
    discard: bool = False
    stop_sent: bool = False
    reason: str = "space"
    tail: list = dataclasses.field(default_factory=list)


class Session:
    """Own recording boundaries; all motion stays in the supplied teleop."""

    # One session coordinates independently owned device/recording resources.
    # pylint: disable=too-many-instance-attributes
    def __init__(self, motion, recorder, readers, snapshot, output):
        self.motion, self.recorder, self.readers = motion, recorder, readers
        self.snapshot, self.output = snapshot, output
        self.phase = "idle"
        self.active = None
        self.completed = []
        self.quit = False
        self.last_key = 0
        self.receipts = {}
        self.closed = False
        self._report("active")

    @property
    def state(self):
        """Show disk finalization explicitly instead of claiming readiness."""
        return self.motion.state if self.phase == "idle" else self.phase

    @property
    def done(self):
        """Normal exit waits for the active recorded episode to commit."""
        return (
            self.quit
            and self.phase == "idle"
            and self.motion.state
            in ("needs_home", "ready", "held", "waiting_leader", "engaging")
        )

    def _report(self, status):
        filesystem.write_json(
            self.output / "session.json",
            {
                "schema_version": 1,
                "state": status,
                "episodes": self.completed,
                "active_episode": (
                    self.active.path.name if self.active else None
                ),
                "snapshot": self.snapshot,
            },
        )

    def key(self, key, now):
        """Space begins/ends; a discards; q drains and ends normally."""
        if key not in (" ", "a", "q"):
            return
        if key == "q":
            self._quit(now)
            return
        previous, self.last_key = self.last_key, now
        if now - previous < 750_000_000:
            return
        if key == "a":
            self._discard(now)
            return
        if self.phase == "recording":
            self._stop(now, "space")
        elif self.phase == "engaging" and self.motion.state == "ready":
            self.motion.key(key, now)
        elif self.phase == "idle" and not self.quit:
            if self.motion.state == "ready":
                path = self.output / f"episode-{len(self.completed):04d}"
                self.active = Episode(
                    path,
                    records.Records(
                        self.snapshot["control"],
                        simulated=self.snapshot["simulated"],
                    ),
                )
                self.recorder.send("prepare", str(path))
                self.phase = "preparing"
                self._report("active")
                print(f"Preparing {path.name}", flush=True)
            else:
                self.motion.key(key, now)

    def _discard(self, now):
        if self.phase in ("preparing", "engaging"):
            print("Not recording yet; q cancels preparation.", flush=True)
            return
        if self.active:
            self.active.discard = True
        if self.phase == "recording":
            self._stop(now, "discard")
        elif self.phase == "idle" and self.completed:
            last = self.completed[-1]
            write_outcome(self.output / last["episode"], "discarded")
            last["disposition"] = "discarded"
            self._report("active")

    def _quit(self, now):
        self.quit = True
        if self.phase == "recording":
            self._stop(now, "session_end")
        elif self.motion.state == "homing":
            self.motion.stop(now)
        elif self.phase in ("preparing", "engaging"):
            self.phase = "idle"
            self.active = None  # Unstarted preparation remains a partial.

    def _stop(self, now, reason):
        # Stop dispatch always precedes IPC or filesystem work.
        self.motion.stop(now)
        if self.motion.state != "stopping":
            raise model.ControlError("recording stop did not revoke following")
        self.active.cutoff, self.active.reason = now, reason
        self.phase = "stopping"

    def _begin(self):
        active = self.active
        active.start = self.motion.input.conditioner.target.created_ns
        context = self.motion.input.context() | {
            "gripper_reference": dataclasses.asdict(
                self.motion.gripper_reference
            )
        }
        event = active.records.authority(
            "acquired", "space", active.start, context
        )
        self.recorder.send("begin", (active.start, event))
        self.phase = "recording"
        print(
            f"Recording {active.path.name}; "
            "Space stops, a discards, q finishes session.",
            flush=True,
        )

    def _samples(self, measured):
        active = self.active
        samples = []
        if self.phase == "recording":
            target = self.motion.controller.progress.target
            if target.sequence > active.last_target:
                request = self.motion.gripper_reference.position(
                    self.motion.input.reading.raw[6]
                )
                intent = active.records.intent(target, self.motion.input)
                samples.extend(
                    (
                        dataclasses.replace(
                            intent, gripper_request_raw=request
                        ),
                        active.records.sent(target, time.monotonic_ns()),
                    )
                )
                active.last_target = target.sequence
        for value in measured:
            stamp = value.provenance.time.received_monotonic_ns
            if stamp >= active.start and (
                not active.cutoff or stamp < active.cutoff
            ):
                samples.extend(active.records.observed(value))
        watermark = active.cutoff or time.monotonic_ns()
        if samples:
            self.recorder.send("samples", (watermark, tuple(samples)))

    def _replies(self):
        for operation, result in self.recorder.poll():
            if operation == "prepare":
                if self.phase != "preparing":
                    if self.quit:
                        continue
                    raise model.ControlError("unexpected writer preparation")
                self.motion.key(" ", time.monotonic_ns())
                self.phase = "engaging"
            elif operation == "complete":
                if self.phase != "finalizing":
                    raise model.ControlError("unexpected episode completion")
                disposition = "discarded" if self.active.discard else "retained"
                write_outcome(self.active.path, disposition)
                self.completed.append(
                    result
                    | {
                        "disposition": disposition,
                        "stop_confirmed_monotonic_ns": self.active.settled_ns,
                    }
                )
                print(
                    f"Saved {self.active.path.name}: "
                    f"MCAP verified, {disposition}.",
                    flush=True,
                )
                self.active = None
                self.phase = "idle"
                self._report("active")

    def step(self, now):
        """Poll storage and output-only readers without blocking motion."""
        self._replies()
        measured = self.readers.read()
        for sample in measured:
            self.receipts[sample.kind] = (
                sample.provenance.time.received_monotonic_ns
            )
        self.motion.step(now)
        if self.phase == "engaging":
            if self.motion.state == "following":
                self._begin()
        if self.phase == "recording":
            self._samples(measured)
        elif self.phase == "stopping":
            active = self.active
            if not active.stop_sent:
                # Wait for both FIFO streams to cross the cutoff.
                active.tail.extend(measured)
                if all(
                    self.receipts.get(k, 0) >= active.cutoff
                    for k in ("ur_feedback", "hande_feedback")
                ):
                    self._samples(active.tail)
                    active.tail.clear()
                    event = active.records.authority(
                        "released", active.reason, active.cutoff
                    )
                    self.recorder.send("stop", (active.cutoff, event))
                    active.stop_sent = True
            if active.stop_sent and self.motion.state == "held":
                active.settled_ns = now
                self.recorder.send("settled")
                self.phase = "finalizing"
                print(
                    "Motion held; verifying MCAP before the next episode...",
                    flush=True,
                )

    def close(self):
        """Abort unfinished output; preserve completed files."""
        if self.closed:
            return
        self.closed = True
        normal = self.done
        self.readers.request_stop()
        self.recorder.abort.set()
        try:
            self.motion.close()
        except BaseException:
            self._report("failed")
            raise
        self._report("complete" if normal else "interrupted")
