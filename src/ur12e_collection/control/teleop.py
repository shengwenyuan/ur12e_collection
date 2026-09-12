"""Native control-only teleoperation, independent of any follower backend."""

import time

from ur12e_collection import timing
from ur12e_collection.control import (
    guards as guarding,
    model,
    owner,
    runtime,
    settling,
)
from ur12e_collection.leader import input as leader_input
from ur12e_collection.leader import mapping


# The fields describe one input/owner interval, not independent controllers.
# pylint: disable=too-many-instance-attributes
class Teleoperation:
    """Own one mapped input and one primary plus optional command twins."""

    # Separate keyword policies preserve the existing simulator constructor.
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        transport,
        leader,
        calibration,
        limits,
        closing_sign=1,
        *,
        guards=None,
        home_open_gripper=True,
    ):
        self.guards = guards
        self.tracking = guarding.Tracking(guards) if guards else None
        self.home_open_gripper = home_open_gripper
        self.controller = owner.Controller(transport, limits)
        self.closing_sign = closing_sign
        self.gripper_reference = None
        self.source = leader
        self.calibration, self.limits = calibration, limits
        self.input = None
        self.state = "needs_home"
        self.last_key_ns = 0
        self.commands = 0
        self.held = None

    def key(self, key, now_ns):
        """Space requests HOME, starts following, or stops in place."""
        if key != " ":
            return
        previous, self.last_key_ns = self.last_key_ns, now_ns
        if now_ns - previous < 750_000_000:
            return
        if self.state in ("needs_home", "held"):
            if self.home_open_gripper:
                self.controller.transport.gripper(0)
            self.controller.go_ready(now_ns)
            self.state = "homing"
        elif self.state == "ready":
            if not self.controller.progress.feedback.gripper_open:
                print("Open and empty the gripper before starting.", flush=True)
                return
            self.state = "engaging"
        elif self.state == "engaging":
            self.state = "ready"
        elif self.state in ("following", "homing"):
            if self.input is not None:
                self.input.close()
            self.controller.halt(now_ns)
            self.state = "stopping"

    def _engage(self, now_ns):
        """Wait for fresh feedback before capturing the start reference."""
        age = now_ns - self.controller.progress.feedback.received_ns
        if not 0 <= age <= min(100_000_000, self.limits.freshness_ns):
            return
        self.input = leader_input.Input(
            self.source,
            self.calibration,
            self.limits,
            self.controller.progress.feedback,
            now_ns,
            guards=self.guards,
        )
        self.gripper_reference = mapping.GripperReference(
            self.input.reading.raw[6], self.closing_sign
        )
        if not self.controller.progress.feedback.gripper_open:
            raise model.ControlError("gripper no longer open at engagement")
        self.controller.engage(self.input.sample(now_ns), now_ns)
        if self.tracking is not None:
            self.tracking.since = None
        self.state = "following"

    def step(self, now_ns):
        """Pump native input continuously and keep primary feedback required."""
        self.source.samples(now_ns)
        self.controller.tick(now_ns)
        if (
            self.guards is not None
            and max(map(abs, self.controller.progress.feedback.qd))
            > self.guards.measured_speed
        ):
            raise model.ControlError("actual joint speed exceeded test limit")
        if (
            self.state == "homing"
            and self.controller.state == "hold"
            and (
                not self.home_open_gripper
                or self.controller.progress.feedback.gripper_open
            )
        ):
            self.state = "ready"
            self.held = self.controller.progress.feedback.q
        elif self.state == "engaging":
            self._engage(time.monotonic_ns())
        elif self.state == "following":
            if self.tracking is not None:
                self.tracking.check(
                    self.controller.progress.target.q,
                    self.controller.progress.feedback,
                    now_ns,
                )
            target = self.input.sample(time.monotonic_ns())
            self.controller.transport.gripper(
                self.gripper_reference.position(self.input.reading.raw[6])
            )
            self.controller.follow(target, time.monotonic_ns())
            self.commands += 1
        elif self.state == "stopping" and self.controller.state == "hold":
            self.state = "held"
            self.held = self.controller.progress.feedback.q
        elif self.guards is not None and self.state in ("ready", "held"):
            measured = self.controller.progress.feedback
            if (
                max(map(abs, measured.qd)) > settling.HOLD_SPEED
                or model.distance(self.held, measured.q) > settling.HOLD_DRIFT
            ):
                raise model.ControlError("arm moved while held")

    def close(self):
        """Stop through the shared owner; never silently return HOME."""
        if self.input is not None:
            self.input.close()
        self.controller.close()
        self.state = "closed"


def run(path, stream, *, operator_approved=False, preflight_only=False):
    """Select a configured adapter without duplicating the control loop."""
    return runtime.launch(
        path,
        stream,
        Teleoperation,
        drive,
        operator_approved=operator_approved,
        preflight_only=preflight_only,
    )


def drive(session, read_keys, log=None):
    """Run one owner; stale input and I/O errors propagate into stop cleanup."""
    print("Space HOME/start/stop; Ctrl+C stop and exit.")
    print("Support the leader. No leader motor writes. Recording is disabled.")
    previous = None
    deadline = time.monotonic_ns()
    while True:
        session.step(time.monotonic_ns())
        if session.state != previous:
            print(f"teleop: {session.state}", flush=True)
            if log:
                log.emit("state", state=session.state)
                if session.state == "following":
                    log.emit(
                        "engaged",
                        context=session.input.context(),
                        gripper_reference=session.gripper_reference,
                    )
            previous = session.state
        if log:
            active = session.input
            log.emit(
                "sample",
                feedback=session.controller.progress.feedback,
                target=session.controller.progress.target,
                leader=active.evidence() if active else None,
                desired=active.desired if active else None,
            )
        # A burst is one operator intent, never multiple future operations.
        keys = read_keys()
        if keys:
            session.key(keys[0], time.monotonic_ns())
        deadline = timing.next_deadline(
            deadline, time.monotonic_ns(), round(1e9 / 120)
        )
        time.sleep(max(0, (deadline - time.monotonic_ns()) / 1e9))
