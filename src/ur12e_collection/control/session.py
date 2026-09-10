"""One keyboard/control owner with injected recording and devices."""

import contextlib
import dataclasses
import json
import os
import pathlib
import time
from typing import Any

from ur12e_collection.control import lifecycle, model, owner, records


def write_outcome(destination: pathlib.Path, disposition: str) -> None:
    """Preserve verified data; atomically replace only the review decision."""
    path = destination / "outcome.json"
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(
            {
                "schema_version": 1,
                "disposition": disposition,
                "task_success": None,
            },
            stream,
        )
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


@dataclasses.dataclass
class Active:
    """Resources and results belonging to exactly one ownership interval."""

    stack: contextlib.ExitStack = dataclasses.field(
        default_factory=contextlib.ExitStack
    )
    program: Any = None
    leader: Any = None
    records: Any = None
    destination: pathlib.Path | None = None
    report: dict | None = None
    held: tuple | None = None
    observed: model.State | None = None
    observed_progress_ns: int = 0
    started_ns: int = 0


@dataclasses.dataclass(frozen=True)
class Setup:
    """Aligned control profile, source factory and immutable episode context."""

    limits: model.Limits
    leader_factory: Any
    snapshot: dict
    output: pathlib.Path


class Session:
    """Call key and step from one control loop; failures latch until restart."""

    def __init__(self, station, recorder, setup: Setup, observer=None):
        self.station, self.recorder = station, recorder
        self.setup = setup
        self.snapshot, self.output = setup.snapshot, setup.output
        self.lifecycle = lifecycle.Lifecycle()
        self.active = Active()
        self.completed = []
        self.timings = []
        self.observer = observer

    @property
    def state(self) -> str:
        """Expose the user-visible lifecycle without authorizing transitions."""
        return self.lifecycle.state

    def key(self, key: str, now_ns: int) -> None:
        """Dispatch a distinct Space/a press; never enqueue future motion."""
        operation = self.lifecycle.key(key, now_ns)
        try:
            if operation == "home":
                self.active.program = self.active.stack.enter_context(
                    self.station.home()
                )
                self.active.program.start()
            elif operation == "prepare":
                self._prepare()
            elif operation == "stop":
                self._stop(
                    now_ns, "discard" if self.lifecycle.discard else "space"
                )
            elif operation == "discard":
                write_outcome(self.active.destination, "discarded")
        except BaseException:
            self.fail()
            raise

    def _prepare(self):
        self.active = Active()
        transport = self.active.stack.enter_context(self.station.motion())
        self.active.program = owner.Controller(
            transport, self.setup.limits, self.snapshot["control"]["leader_id"]
        )
        self.active.program.tick(time.monotonic_ns())
        self.active.destination = (
            self.output / f"episode-{len(self.completed):04d}"
        )
        self.active.records = records.Records(
            self.snapshot["control"], simulated=self.snapshot["simulated"]
        )
        self.recorder.send("prepare", str(self.active.destination))

    def _begin(self):
        program = self.active.program
        program.tick(time.monotonic_ns())
        now = time.monotonic_ns()
        self.active.started_ns = now
        self.active.leader = self.setup.leader_factory(
            program.progress.feedback.q, now
        )
        initial = self.active.leader.sample(now)
        event = self.active.records.authority("acquired", "space", now)
        self.recorder.send("begin", (now, event))
        if self.observer is not None:
            self.observer.records((event,))
        program.engage(initial, now)
        self.lifecycle.complete("prepare")

    def _stop(self, now_ns, reason):
        event = self.active.records.authority("released", reason, now_ns)
        self.recorder.send("stop", (now_ns, event))
        if self.observer is not None:
            self.observer.records((event,))
        self.active.program.halt(now_ns)

    def step(self) -> None:
        """Feed the current SDK owner and supervise independent recording."""
        try:
            for operation, value in self.recorder.poll():
                if operation == "prepare":
                    if self.state != "preparing":
                        raise model.ControlError("unexpected preparation reply")
                    self._begin()
                elif operation == "complete":
                    self.active.report = value
            self._motion()
            if self.state == "finalizing" and self.active.report is not None:
                disposition = (
                    "discarded" if self.lifecycle.discard else "retained"
                )
                write_outcome(self.active.destination, disposition)
                self.completed.append(self.active.report)
                self.lifecycle.complete("finalize")
            if self.observer is not None:
                destination = self.active.destination
                self.observer.status(
                    self.state, destination.name if destination else None
                )
        except BaseException:
            self.fail()
            raise

    def _motion(self):
        active = self.active
        if self.state == "homing":
            active.program.step()
            if active.program.state == "hold":
                active.held = active.program.feedback.q
                self._release()
                self.lifecycle.complete("home")
        elif self.state in ("preparing", "recording", "stopping"):
            state = active.program.tick(time.monotonic_ns())
            if self.state == "recording":
                target = active.leader.sample(time.monotonic_ns())
                intent = active.records.intent(target)
                active.program.follow(target, time.monotonic_ns())
                sent = active.records.sent(target, time.monotonic_ns())
                samples = (intent, sent, *active.records.feedback(state))
                self.recorder.send("samples", (time.monotonic_ns(), samples))
                if self.observer is not None:
                    self.observer.records(samples)
            elif self.state == "stopping" and active.program.state == "hold":
                active.held = state.q
                self.recorder.send("settled")
                self._release()
                self.lifecycle.complete("stop")
        elif self.state in ("ready", "held", "finalizing"):
            self._hold()

    def _hold(self):
        active = self.active
        state = self.station.read()
        now = time.monotonic_ns()
        self.setup.limits.check(state.q)
        if (
            active.observed is None
            or state.timestamp > active.observed.timestamp
        ):
            active.observed_progress_ns = now
        elif state.timestamp < active.observed.timestamp:
            raise model.ControlError("held controller timestamp moved backward")
        if (
            not 0 <= now - state.received_ns <= self.setup.limits.freshness_ns
            or now - active.observed_progress_ns
            > self.setup.limits.freshness_ns
        ):
            raise model.ControlError("held feedback is stale")
        active.observed = state
        if (
            (state.robot_mode, state.safety_mode, state.runtime_state)
            != (7, 1, 1)
            or max(map(abs, state.qd)) >= self.setup.limits.stopped_speed
            or model.distance(state.q, active.held) > self.setup.limits.arrival
        ):
            raise model.ControlError("released arm did not hold its pose")

    def _release(self):
        started = time.monotonic_ns()
        if self.active.program is not None:
            self.active.program.close()
            self.active.program = None
        self.active.stack.close()
        self.timings.append(
            {
                "operation": "release",
                "elapsed_ms": (time.monotonic_ns() - started) / 1e6,
            }
        )

    def fail(self) -> None:
        """Revoke recording and active motion; no automatic HOME or recovery."""
        self.recorder.abort.set()
        self.lifecycle.fail()
        program = self.active.program
        if isinstance(program, owner.Controller):
            program.fail("session ownership failed")
        self._release()

    def close(self) -> None:
        """Interrupted work remains partial; completed held episodes survive."""
        try:
            if self.state not in ("needs_home", "ready", "held", "closed"):
                self.fail()
            else:
                self._release()
        finally:
            self.recorder.close()
            self.lifecycle.close()
            if self.observer is not None:
                self.observer.status(self.state, None)
                self.observer.close()
