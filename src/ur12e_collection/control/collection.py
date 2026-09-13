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


@dataclasses.dataclass
class Rejection:
    """One interrupted interval and the operator's pending disposition."""

    reason: str
    unavailable: set = dataclasses.field(default_factory=set)
    choice: str | None = None


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
        self.rejection = None
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
            and self.active is None
            and self.phase in ("idle", "blocked")
            and (
                self.motion.state
                in ("needs_home", "ready", "held", "waiting_leader", "engaging")
                or (
                    self.rejection is not None
                    and "motion" in self.rejection.unavailable
                )
            )
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
                "rejection": self.rejection.reason if self.rejection else None,
            },
        )

    def key(self, key, now):
        """Keep operator input alive when a transition is rejected."""
        try:
            self._key(key, now)
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._reject("session", error, time.monotonic_ns())

    def _key(self, key, now):
        if key not in (" ", "a", "q"):
            return
        if key == "q":
            self._quit(now)
            return
        previous, self.last_key = self.last_key, now
        if now - previous < 750_000_000:
            return
        if self.phase == "review":
            self.rejection.choice = "abort" if key == "a" else "save"
            return
        if self.phase == "blocked":
            print(
                "Session unavailable; q exits. No motion will resume.",
                flush=True,
            )
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
        if self.rejection:
            if self.phase == "review":
                self.rejection.choice = "save"
            return
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
                    if self.quit or self.rejection:
                        continue
                    raise model.ControlError("unexpected writer preparation")
                self.motion.key(" ", time.monotonic_ns())
                self.phase = "engaging"
            elif operation == "cancelled":
                if self.phase != "cancelling":
                    raise model.ControlError("unexpected episode cancellation")
                self._partial()
            elif operation == "complete":
                if self.phase != "finalizing":
                    raise model.ControlError("unexpected episode completion")
                disposition = "discarded" if self.active.discard else "retained"
                write_outcome(
                    self.active.path,
                    disposition,
                    interruption=(
                        self.rejection.reason if self.rejection else None
                    ),
                )
                self.completed.append(
                    result
                    | {
                        "disposition": disposition,
                        "stop_confirmed_monotonic_ns": self.active.settled_ns,
                        "interruption": (
                            self.rejection.reason if self.rejection else None
                        ),
                    }
                )
                print(
                    f"Saved {self.active.path.name}: "
                    f"MCAP verified, {disposition}.",
                    flush=True,
                )
                self.active = None
                self.phase = "resolving" if self.rejection else "idle"
                self._report("active")

    def _guarded(self, component, operation):
        """Contain a failed component without retrying its broken connection."""
        if self.rejection and component in self.rejection.unavailable:
            return None
        try:
            return operation()
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._reject(component, error, time.monotonic_ns())
            return None

    def _reject(self, component, error, now):
        if self.rejection:
            if component != "session":
                self.rejection.unavailable.add(component)
            print(f"{component} unavailable: {error}", flush=True)
            if component == "motion":
                self.motion.controller.fail(str(error))
        else:
            choice = "save" if self.quit else None
            if self.active and self.active.discard:
                choice = "abort"
            self.rejection = Rejection(str(error), choice=choice)
            if component not in ("motion", "session"):
                self.rejection.unavailable.add(component)
            if self.active:
                if self.active.start and not self.active.cutoff:
                    self.active.cutoff = now
                self.active.reason = f"rejected: {error}"
            # Revoke motion before touching storage or waiting for user input.
            try:
                self.motion.reject(str(error), now)
            # Stop failures must not remove the operator disposition entry.
            # pylint: disable-next=broad-exception-caught
            except Exception as error_stop:
                self.rejection.unavailable.add("motion")
                print(f"Stop unconfirmed: {error_stop}", flush=True)
            if self.motion.state == "blocked":
                self.rejection.unavailable.add("motion")
            if self.phase != "finalizing":
                self.phase = "review"
            print(
                "Collection paused: Space saves valid data; "
                "a abandons this episode; q finishes the session.",
                flush=True,
            )
        if component == "recorder":
            self.recorder.abort.set()
            self.phase = "review"
        self._report("rejected")

    def step(self, now):
        """Keep motion supervision, healthy sources and keyboard independent."""
        self._guarded("recorder", self._replies)
        measured = self._guarded("readers", self.readers.read) or []
        for sample in measured:
            self.receipts[sample.kind] = (
                sample.provenance.time.received_monotonic_ns
            )
        self._guarded("motion", lambda: self.motion.step(now))
        if self.phase == "engaging" and self.motion.state == "following":
            self._guarded("recorder", self._begin)
        if self.phase == "recording":
            self._guarded("recorder", lambda: self._samples(measured))
        elif self.phase in ("stopping", "review"):
            if self.active and self.active.start:
                if self.motion.state == "held" and not self.active.settled_ns:
                    self.active.settled_ns = now
                if not self.rejection or not self.rejection.unavailable:
                    self._guarded("recorder", lambda: self._tail(measured))
            if self.phase == "stopping" and self.motion.state == "held":
                if self.active.stop_sent:
                    self._guarded("recorder", self._finalize)
            elif self.phase == "review":
                # Disposition must remain callable even with a failed recorder.
                self._guarded("session", self._review)
        elif self.phase == "resolving":
            self._resolved()

    def _tail(self, measured):
        active = self.active
        if not active.stop_sent:
            # Wait for both FIFO streams to cross the cutoff.
            active.tail.extend(
                sample
                for sample in measured
                if sample.provenance.time.received_monotonic_ns < active.cutoff
            )
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

    def _finalize(self):
        self.recorder.send("settled")
        self.phase = "finalizing"
        print(
            "Motion held; verifying MCAP before the next episode...", flush=True
        )

    def _review(self):
        choice = self.rejection.choice
        if choice is None:
            return
        if self.active is None:
            self.phase = "resolving"
            self._resolved()
        elif choice == "abort" or not self.active.start:
            self._cancel()
        elif self.rejection.unavailable:
            print(
                "Cannot verify this episode; partial data remains available.",
                flush=True,
            )
            self.rejection.choice = None
            if self.quit:
                self._cancel()
        elif self.motion.state == "held" and self.active.stop_sent:
            self._guarded("recorder", self._finalize)

    def _cancel(self):
        if "recorder" in self.rejection.unavailable:
            self._partial()
        else:
            self.phase = "cancelling"
            self._guarded("recorder", lambda: self.recorder.send("cancel"))

    def _partial(self):
        self.completed.append(
            {
                "episode": self.active.path.name + ".partial",
                "disposition": (
                    "discarded"
                    if self.rejection.choice == "abort"
                    else "incomplete"
                ),
                "interruption": self.rejection.reason,
                "verified": False,
            }
        )
        self.active = None
        self.phase = "resolving"
        self._report("rejected")

    def _resolved(self):
        if self.rejection.unavailable:
            self.phase = "blocked"
        elif self.motion.state == "held":
            self.rejection = None
            self.phase = "idle"
            print("Episode handled. Space requests HOME; q exits.", flush=True)
        else:
            return
        self._report("active" if self.phase == "idle" else "rejected")

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
