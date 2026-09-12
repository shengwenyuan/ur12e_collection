"""One required primary and bounded, optional command twins."""

import queue
import threading

from ur12e_collection.followers import kinematic, local


class Twin:
    """An optional follower cannot block or acquire the primary owner."""

    def __init__(self, factory):
        self.factory = factory
        self.pending = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.fault = None
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def offer(self, operation, args):
        """Replace superseded commands without waiting for the consumer."""
        try:
            self.pending.get_nowait()
        except queue.Empty:
            pass
        try:
            self.pending.put_nowait((operation, args))
        except queue.Full:
            pass

    def run(self):
        """Own only this optional transport; failure stays explicitly local."""
        transport = None
        try:
            transport = self.factory()
            while not self.stop.is_set():
                try:
                    operation, args = self.pending.get(timeout=0.05)
                    getattr(transport, operation)(*args)
                except queue.Empty:
                    pass
                feedback = transport.read()
                if feedback and not feedback.motion_allowed:
                    raise RuntimeError(feedback.motion_error)
                transport.heartbeat()
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.fault = str(error)
        finally:
            if transport is not None:
                transport.close()

    def close(self):
        """Revoke this consumer without waiting on an optional device."""
        self.stop.set()


class Group:
    """Fan out only after the primary accepts a bounded command."""

    def __init__(self, primary, twins=()):
        self.primary = primary
        self.gripper_position = None
        self.twins = tuple(Twin(factory) for factory in twins)

    def read(self):
        """Only required primary feedback drives control decisions."""
        return self.primary.read()

    def _send(self, operation, *args):
        getattr(self.primary, operation)(*args)
        for twin in self.twins:
            twin.offer(operation, args)

    def gripper(self, position):
        """Stage the gripper component of the next atomic arm/tool command."""
        self.gripper_position = kinematic.gripper_position(position)

    def _motion(self, operation, *args):
        if self.gripper_position is not None:
            args += (self.gripper_position,)
        self._send(operation, *args)

    def move(self, q, speed, acceleration):
        """Dispatch a primary-accepted HOME or route command."""
        self._motion("move", q, speed, acceleration)

    def servo(self, q):
        """Dispatch one primary-accepted servo target."""
        self._motion("servo", q)

    def stop(self, servo):
        """Revoke primary motion before notifying optional twins."""
        try:
            self.primary.stop(servo)
        finally:
            for twin in self.twins:
                twin.offer("stop", (servo,))

    def heartbeat(self):
        """Optional consumers refresh their own watchdog independently."""
        self.primary.heartbeat()

    def close(self):
        """Release the primary first; optional cleanup never blocks it."""
        try:
            self.primary.close()
        finally:
            for twin in self.twins:
                twin.close()


def open_group(config):
    """Open only configured native simulation endpoints; never UR sockets."""
    primary = local.Transport(config["follower"]["endpoint"])
    factories = [
        lambda endpoint=value["endpoint"]: local.Transport(endpoint)
        for value in config.get("twins", [])
    ]
    return Group(primary, factories)
