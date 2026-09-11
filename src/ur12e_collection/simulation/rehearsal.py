"""Disposable motion preview; no production session, cameras or recorder."""

import contextlib
import json
import pathlib
import time

from ur12e_collection import timing
from ur12e_collection.control import console, owner
from ur12e_collection.leader import input as leader_input
from ur12e_collection.simulation import connection, live_leader, profile


class Preview:
    """Explicit HOME/start/stop with an immutable reference per engagement."""

    def __init__(self, station, live):
        self.station, self.live = station, live
        self.state = "needs_home"
        self.stack = contextlib.ExitStack()
        self.program, self.leader = None, None
        self.events = []
        self.commands = 0

    def event(self, name, **details):
        """Keep transition diagnostics, not a collection episode."""
        self.events.append(
            {"event": name, "monotonic_ns": time.monotonic_ns(), **details}
        )

    def key(self, key):
        """Only Space changes motion; no recording or discard operation."""
        if key != " ":
            return
        if self.state in ("needs_home", "held"):
            self.program = self.stack.enter_context(self.station.home())
            self.program.start()
            self.state = "homing"
            self.event("home_requested")
        elif self.state == "ready":
            self._begin()
        elif self.state == "following":
            self._stop("space")

    def _begin(self):
        # Check readiness before uploading the SDK program, then capture a new
        # reference after handover. Neither check writes to the physical leader.
        try:
            probe = leader_input.Input(
                self.live,
                self.live.calibration,
                profile.LIMITS,
                self.station.read(),
                time.monotonic_ns(),
                freshness_ns=live_leader.INPUT_AGE_NS,
            )
            probe.close()
        except ValueError as error:
            self.event("start_waiting", reason=str(error))
            print(f"rehearsal: waiting for stable input ({error})", flush=True)
            return
        transport = self.stack.enter_context(self.station.motion())
        self.program = owner.Controller(transport, profile.LIMITS)
        self.program.tick(time.monotonic_ns())
        try:
            self.leader = leader_input.Input(
                self.live,
                self.live.calibration,
                profile.LIMITS,
                self.program.progress.feedback,
                time.monotonic_ns(),
                freshness_ns=live_leader.INPUT_AGE_NS,
            )
            initial = self.leader.sample(time.monotonic_ns())
        except ValueError as error:
            self._release()
            self.event("start_waiting", reason=str(error))
            print(f"rehearsal: waiting for stable input ({error})", flush=True)
            return
        self.program.engage(initial, time.monotonic_ns())
        self.state = "following"
        self.event("following", reference=self.leader.context())

    def _stop(self, reason, error=None):
        self.program.halt(time.monotonic_ns())
        self.leader.close()
        self.state = "stopping"
        self.event(
            "stop_requested", reason=reason, error=str(error) if error else None
        )
        if error:
            print(
                "rehearsal: input expired; stopping. Space after hold: HOME.",
                flush=True,
            )

    def step(self):
        """Idle expiry can recover; following expiry stops without resuming."""
        try:
            self.live.samples(time.monotonic_ns())
        except live_leader.Unavailable as error:
            if self.state == "following":
                self._stop("input_expired", error)
        if self.state == "homing":
            self.program.step()
            if self.program.state == "hold":
                self._release()
                self.state = "ready"
                self.event("home_complete")
        elif self.state in ("following", "stopping"):
            self.program.tick(time.monotonic_ns())
            if self.state == "following":
                try:
                    target = self.leader.sample(time.monotonic_ns())
                except live_leader.Unavailable as error:
                    self._stop("input_expired", error)
                    return
                self.program.follow(target, time.monotonic_ns())
                self.commands += 1
            elif self.program.state == "hold":
                self._release()
                self.state = "held"
                self.event("stopped")

    def _release(self):
        try:
            if self.leader is not None:
                self.leader.close()
            if self.program is not None:
                self.program.close()
        finally:
            self.stack.close()
            self.program, self.leader = None, None

    def close(self):
        """Active closure invokes the shared owner's stop, never HOME."""
        self._release()


def run(output, revision, stream, live_config):
    """Run only against the isolated simulator and retain a small report."""
    permit = json.loads(
        pathlib.Path("/sim-permit.json").read_text(encoding="utf-8")
    )
    if revision != permit["source_revision"]:
        raise ValueError("requested revision differs from simulator source")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "kind": "motion_rehearsal",
        "production_acceptance": False,
        "recording": False,
        "motor_writes": False,
        "revision": revision,
        "state": "failed",
    }
    preview = None
    try:
        with (
            console.keyboard(stream) as read_keys,
            live_leader.Live(*live_config) as live,
            connection.open_station() as station,
        ):
            preview = Preview(station, live)
            previous = None
            deadline = time.monotonic_ns()
            try:
                while True:
                    if previous != preview.state:
                        print(f"rehearsal: {preview.state}", flush=True)
                        previous = preview.state
                    for key in read_keys():
                        preview.key(key)
                    preview.step()
                    deadline = timing.next_deadline(
                        deadline,
                        time.monotonic_ns(),
                        round(1e9 / profile.COMMAND_HZ),
                    )
                    time.sleep(max(0, (deadline - time.monotonic_ns()) / 1e9))
            except (KeyboardInterrupt, EOFError):
                report["state"] = "interrupted"
            finally:
                preview.close()
    except Exception as error:
        report["state"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        if preview is not None:
            report.update(events=preview.events, commands=preview.commands)
        (output / "rehearsal.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    return report
