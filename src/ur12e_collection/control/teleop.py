"""Native control-only teleoperation, independent of any follower backend."""

import sys
import time

from ur12e_collection import timing
from ur12e_collection.control import console, owner
from ur12e_collection.followers import config as configuration
from ur12e_collection.followers import dispatch
from ur12e_collection.leader import input as leader_input
from ur12e_collection.leader import mapping, native


class Teleoperation:
    """Own one mapped input and one primary plus optional command twins."""

    def __init__(self, transport, leader, calibration, limits, closing_sign=1):
        self.controller = owner.Controller(transport, limits)
        self.closing_sign = closing_sign
        self.gripper_reference = None
        self.source = leader
        self.calibration, self.limits = calibration, limits
        self.input = None
        self.state = "needs_home"
        self.last_key_ns = 0
        self.commands = 0

    def key(self, key, now_ns):
        """Space requests HOME, starts following, or stops in place."""
        if key != " " or now_ns - self.last_key_ns < 250_000_000:
            return
        self.last_key_ns = now_ns
        if self.state in ("needs_home", "held"):
            self.controller.transport.gripper(0)
            self.controller.go_ready(now_ns)
            self.state = "homing"
        elif self.state == "ready":
            self.state = "engaging"
        elif self.state == "engaging":
            self.state = "ready"
        elif self.state == "following":
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
        )
        self.gripper_reference = mapping.GripperReference(
            self.input.reading.raw[6], self.closing_sign
        )
        self.controller.engage(self.input.sample(now_ns), now_ns)
        self.state = "following"

    def step(self, now_ns):
        """Pump native input continuously and keep primary feedback required."""
        self.source.samples(now_ns)
        self.controller.tick(now_ns)
        if (
            self.state == "homing"
            and self.controller.state == "hold"
            and self.controller.progress.feedback.gripper_open
        ):
            self.state = "ready"
        elif self.state == "engaging":
            self._engage(time.monotonic_ns())
        elif self.state == "following":
            target = self.input.sample(time.monotonic_ns())
            self.controller.transport.gripper(
                self.gripper_reference.position(self.input.reading.raw[6])
            )
            self.controller.follow(target, time.monotonic_ns())
            self.commands += 1
        elif self.state == "stopping" and self.controller.state == "hold":
            self.state = "held"

    def close(self):
        """Stop through the shared owner; never silently return HOME."""
        if self.input is not None:
            self.input.close()
        self.controller.close()
        self.state = "closed"


def run(path, stream):
    """Run the mainline entry on Linux with explicit local configuration."""
    if sys.platform != "linux":
        raise ValueError("native teleoperation runs on the Ubuntu station")
    config = configuration.load(path)
    calibration = mapping.load(config["leader"]["calibration"])
    leader = native.Leader(
        config["leader"]["device"], config["leader"]["baudrate"]
    )
    transport = dispatch.open_group(config)
    session = Teleoperation(
        transport,
        leader,
        calibration,
        config["limits"],
        config["gripper"]["closing_sign"],
    )
    try:
        leader.start()
        with console.keyboard(stream) as read_keys:
            print("Native teleop: Space HOME/start/stop; Ctrl+C stop and exit.")
            print("Support the leader. No motor writes. Recording is disabled.")
            previous = None
            deadline = time.monotonic_ns()
            while True:
                now = time.monotonic_ns()
                session.step(now)
                if session.state != previous:
                    print(f"teleop: {session.state}", flush=True)
                    previous = session.state
                for key in read_keys():
                    session.key(key, time.monotonic_ns())
                deadline = timing.next_deadline(
                    deadline, time.monotonic_ns(), round(1e9 / 120)
                )
                time.sleep(max(0, (deadline - time.monotonic_ns()) / 1e9))
    except (KeyboardInterrupt, EOFError):
        return 130
    finally:
        try:
            session.close()
        finally:
            leader.close()
