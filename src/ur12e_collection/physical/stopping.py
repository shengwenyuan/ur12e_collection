"""One SDK stop operation with a bounded controller-side braking window."""

import threading

from ur12e_collection.control import model


class Stop:
    """The normal owner yields SDK writes until this stop completes."""

    def __init__(self, control, servo, deceleration, emit):
        self.control = control
        self.servo = servo
        self.deceleration = deceleration
        self.emit = emit
        self.done = threading.Event()
        self.error = None
        self.thread = threading.Thread(
            target=self._run, name="ur-stop", daemon=True
        )

    def start(self):
        """Leave acquisition and observation running during stop."""
        self.thread.start()

    def _run(self):
        try:
            # The synchronous SDK servoStop blocks longer than a normal input
            # deadline. Only the already-revoked stopping phase gets 2 seconds.
            if not self.control.setWatchdog(0.5):
                raise model.ControlError("stop watchdog setup failed")
            self.emit(
                "stop_dispatched",
                servo=self.servo,
                deceleration=self.deceleration,
            )
            if self.servo:
                if not self.control.servoStop(self.deceleration):
                    raise model.ControlError("UR did not acknowledge servoStop")
            else:
                self.control.stopJ(self.deceleration, True)
            if (
                not self.control.setWatchdog(5.0)
                or not self.control.kickWatchdog()
            ):
                raise model.ControlError("watchdog restore failed after stop")
            self.emit("stop_acknowledged")
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.error = str(error)
        finally:
            self.done.set()

    def check(self):
        """Retain the first failure; never issue a duplicate stop or resume."""
        if self.error:
            raise model.ControlError(self.error)

    def join(self):
        """Bound local cleanup; a stalled call remains controller-supervised."""
        if not self.done.wait(2):
            raise model.ControlError("SDK stop stalled; stop unconfirmed")
        self.thread.join()
        self.check()
