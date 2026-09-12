"""One bounded Hand-E worker, independent of arm command timing."""

import dataclasses
import socket
import threading
import time

from ur12e_collection.control import gripper


@dataclasses.dataclass(frozen=True)
class Reading:
    """Real registers retain their own acquisition time."""

    registers: tuple
    acquired_ns: int


class Worker:
    """Coalesce new targets; never activate, reset, retry or auto-release."""

    def __init__(self, host, settings):
        self.host, self.settings = host, settings
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.ready = threading.Event()
        self.reading = None
        self.pending = None
        self.error = None
        self.sent = None
        self.thread = threading.Thread(
            target=self._run, name="hande", daemon=True
        )

    def start(self):
        """Await read-only startup before any arm owner is acquired."""
        self.thread.start()
        if not self.ready.wait(3):
            self.close()
            raise RuntimeError("Hand-E startup timed out")
        self.view()

    def view(self):
        """Never relabel cached registers as fresh or commanded position."""
        with self.lock:
            if self.error:
                raise RuntimeError(self.error)
            if (
                self.reading is None
                or not 0
                <= time.monotonic_ns() - self.reading.acquired_ns
                <= 500_000_000
            ):
                raise RuntimeError("Hand-E feedback stale")
            return self.reading

    def offer(self, position):
        """Replace only an unsent request; no queue of old closes/opens."""
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or not 0 <= position <= 255
        ):
            raise ValueError("invalid Hand-E target")
        self.view()
        with self.lock:
            self.pending = position

    def hold(self):
        """Cancel pending work; an acknowledged/in-flight grasp may complete."""
        with self.lock:
            self.pending = None

    def _run(self):
        client = None
        try:
            connection = socket.create_connection(
                (self.host, self.settings["port"]), timeout=1
            )
            client = gripper.Client(connection)
            while not self.done.is_set():
                registers, stamp = client.read()
                values = dict(registers)
                if values["STA"] != 3 or values["FLT"]:
                    raise RuntimeError("Hand-E inactive or faulted")
                with self.lock:
                    self.reading = Reading(registers, stamp)
                    requested, self.pending = self.pending, None
                self.ready.set()
                if requested is not None and requested != self.sent:
                    client.move(
                        requested,
                        self.settings["speed"],
                        self.settings["force"],
                    )
                    self.sent = requested
                self.done.wait(0.05)
        except Exception as error:  # pylint: disable=broad-exception-caught
            with self.lock:
                self.error = str(error)
        finally:
            self.ready.set()
            if client is not None:
                client.close()

    def close(self):
        """Preserve the last grasp request when ownership ends."""
        self.hold()
        self.done.set()
        if self.thread.ident:
            self.thread.join(2)
            if self.thread.is_alive():
                raise RuntimeError("Hand-E worker did not exit")
