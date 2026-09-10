"""Measured execution of a controller-owned, one-shot native Home program."""

import time
from collections.abc import Callable

from ur12e_collection.control.model import ControlError, Limits, State, distance


class NativeHome:
    """No host watchdog: the native program may finish after client loss."""

    def __init__(
        self,
        command: Callable[[str], str],
        read: Callable[[], State],
        limits: Limits,
        program: str,
    ):
        self.command, self.read = command, read
        self.limits, self.program = limits, program
        self.state = "idle"
        self.feedback = None
        self.started_ns = self.progress_ns = 0
        self.settled_ns = None
        self.seen_running = False

    def start(self) -> None:
        """Require an idle controller before transferring native ownership."""
        if self.state != "idle":
            raise ControlError("native HOME requires a fresh owner")
        try:
            state = self._read(time.monotonic_ns())
            if state.runtime_state != 1 or max(map(abs, state.qd)) >= 0.01:
                raise ControlError("native HOME requires a stopped program/arm")
            if self.command("running") != "Program running: false":
                raise ControlError("another native program is running")
            if not self.command("load " + self.program).startswith(
                "Loading program:"
            ):
                raise ControlError("native HOME load failed")
            # Loading must not execute or steal a different running program.
            if self.command("running") != "Program running: false":
                raise ControlError("program started unexpectedly while loading")
            self.started_ns = time.monotonic_ns()
            self.state = "moving"
            if self.command("play") != "Starting program":
                raise ControlError("native HOME start failed")
        except Exception:
            if self.state == "moving":
                self.stop()
            self.state = "fault"
            raise

    def _read(self, now: int) -> State:
        state = self.read()
        self.limits.check(state.q)
        if (state.robot_mode, state.safety_mode) != (7, 1):
            raise ControlError("native HOME controller is not normal")
        age = time.monotonic_ns() - state.received_ns
        if not 0 <= age <= self.limits.freshness_ns:
            raise ControlError("native HOME readback is stale or future")
        if self.feedback is None or state.timestamp > self.feedback.timestamp:
            self.progress_ns = now
        elif state.timestamp < self.feedback.timestamp:
            raise ControlError("native HOME controller time went backward")
        if now - self.progress_ns > self.limits.freshness_ns:
            raise ControlError("native HOME controller time stopped")
        self.feedback = state
        return state

    def step(self) -> State:
        """Check actual arrival or a requested stop without sending motion."""
        if self.state not in ("moving", "stopping", "hold"):
            raise ControlError("native HOME owner is not active")
        now = time.monotonic_ns()
        try:
            state = self._read(now)
            self.seen_running |= state.runtime_state == 2
            if state.runtime_state not in (0, 1, 2):
                raise ControlError("unexpected native program runtime state")
            stopped = (
                state.runtime_state == 1 and max(map(abs, state.qd)) < 0.01
            )
            arrived = distance(state.q, self.limits.ready) < self.limits.arrival
            if self.state == "moving" and stopped and not arrived:
                if self.seen_running or now - self.started_ns > 2_000_000_000:
                    raise ControlError("native HOME ended without arrival")
            timeout = (
                1_000_000_000 if self.state == "stopping" else 60_000_000_000
            )
            if self.state != "hold" and now - self.started_ns > timeout:
                raise ControlError("native HOME motion/stop timed out")
            if stopped and (arrived or self.state in ("stopping", "hold")):
                if self.settled_ns is None:
                    self.settled_ns = now
                if now - self.settled_ns >= 100_000_000:
                    self.state = "hold"
            else:
                self.settled_ns = None
            return state
        except Exception:
            self.stop()
            self.state = "fault"
            raise

    def stop(self) -> None:
        """Explicit cancellation; it does not return to HOME or restart SDK."""
        self.state = "stopping"
        self.started_ns = time.monotonic_ns()
        self.settled_ns = None
        if self.command("stop") != "Stopped":
            self.state = "fault"
            raise ControlError("native HOME stop unconfirmed")

    def close(self) -> None:
        """Cancel an unfinished program on orderly local cleanup."""
        if self.state in ("moving", "stopping"):
            self.stop()
        self.state = "closed"
