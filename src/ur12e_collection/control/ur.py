"""Reusable UR RTDE operations; connection authorization is external."""

import time

from ur12e_collection.control.model import ControlError, State


class URTransport:
    """Own authorized SDK objects; never reconnect or choose a robot address."""

    def __init__(self, control, receiver, period: float = 0.02):
        self.control = control
        self.receiver = receiver
        self.period = period
        self.closed = False

    def read(self) -> State:
        """Bracket getters with uptime; this is not an atomic packet."""
        if not self.control.isConnected() or not self.receiver.isConnected():
            raise ControlError("UR connection lost")
        for _ in range(5):
            stamp = self.receiver.getTimestamp()
            values = (
                tuple(self.receiver.getActualQ()),
                tuple(self.receiver.getActualQd()),
                self.receiver.getRobotMode(),
                self.receiver.getSafetyMode(),
                self.receiver.getRuntimeState(),
            )
            if stamp == self.receiver.getTimestamp():
                return State(
                    values[0],
                    values[1],
                    stamp,
                    time.monotonic_ns(),
                    *values[2:],
                )
        raise ControlError("UR readback changed during every timestamp bracket")

    def move(self, q: tuple, speed: float, acceleration: float) -> None:
        """Start a native asynchronous moveJ with explicit rate limits."""
        if not self.control.moveJ(list(q), speed, acceleration, True):
            raise ControlError("UR rejected moveJ")

    def servo(self, q: tuple) -> None:
        """Controller enforces rates; SDK rate arguments here are unused."""
        if not self.control.servoJ(list(q), 0.0, 0.0, self.period, 0.1, 300):
            raise ControlError("UR rejected servoJ")

    def stop(self, servo: bool) -> None:
        """Use the native stop corresponding to the active motion mode."""
        if servo:
            if not self.control.servoStop(5.0):
                raise ControlError("UR did not acknowledge servoStop")
        else:
            self.control.stopJ(5.0, True)

    def heartbeat(self) -> None:
        """Only active ownership can feed the controller's watchdog."""
        if not self.control.isProgramRunning():
            raise ControlError("UR control program is not running")
        if not self.control.kickWatchdog():
            raise ControlError("UR watchdog update failed")

    def close(self) -> None:
        """End this control program, then close both local SDK connections."""
        if self.closed:
            return
        self.closed = True
        try:
            if self.control.isConnected() and self.control.isProgramRunning():
                self.control.stopScript()
        finally:
            try:
                self.control.disconnect()
            finally:
                self.receiver.disconnect()
