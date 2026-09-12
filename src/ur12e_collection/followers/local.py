"""Bounded same-host Unix stream transport for a native follower service."""

import json
import pathlib
import socket
import time
import uuid

from ur12e_collection.control import model
from ur12e_collection.followers import kinematic

MAX_PACKET = 4096


def encode(value: dict) -> bytes:
    """Keep each command/state message below a fixed transport budget."""
    payload = json.dumps(value, allow_nan=False).encode()
    if len(payload) > MAX_PACKET:
        raise model.ControlError("oversized follower packet")
    return payload


class Frames:
    """Bound partial stream reads without losing message boundaries."""

    def __init__(self):
        self.pending = b""

    def receive(self, connection):
        """Drain a bounded byte budget and return complete JSON messages."""
        result = []
        for _ in range(16):
            try:
                data = connection.recv(MAX_PACKET)
            except BlockingIOError:
                break
            if not data:
                raise EOFError("follower peer disconnected")
            self.pending += data
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                if len(line) > MAX_PACKET:
                    raise model.ControlError("oversized follower frame")
                result.append(line)
            if len(self.pending) > MAX_PACKET:
                raise model.ControlError("oversized partial follower frame")
        return result


def command(data: bytes) -> dict:
    """Validate the local command envelope before granting any ownership."""
    if len(data) > MAX_PACKET:
        raise model.ControlError("oversized follower command")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise model.ControlError("command must be an object")
    for name in ("version", "sequence", "created_ns"):
        number = value.get(name)
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or number < 0
        ):
            raise model.ControlError("invalid command identity or clock")
    if (
        value["version"] != 2
        or not isinstance(value.get("epoch"), str)
        or not 0 < len(value["epoch"]) <= 64
        or value.get("operation")
        not in ("claim", "move", "servo", "stop", "release", "heartbeat")
    ):
        raise model.ControlError("invalid command envelope")
    return value


class Transport:
    """One owner, one endpoint, no host network or robot SDK."""

    def __init__(self, endpoint: pathlib.Path):
        self.epoch = uuid.uuid4().hex
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
        self.socket.settimeout(0.2)
        self.sequence = 0
        self.feedback = None
        self.last_heartbeat = 0.0
        self.closed = False
        self.frames = Frames()
        try:
            self.socket.connect(str(endpoint))
            self.socket.setblocking(False)
            self.send("claim")
            deadline = time.monotonic() + 3
            while self.feedback is None:
                self.read()
                if time.monotonic() > deadline:
                    raise model.ControlError("Isaac did not acknowledge owner")
                time.sleep(0.005)
            if not self.feedback.motion_allowed:
                raise model.ControlError(self.feedback.motion_error)
        except BaseException:
            self.close()
            raise

    def send(self, operation: str, **value):
        """A saturated required endpoint fails instead of blocking control."""
        self.sequence += 1
        payload = (
            encode(
                {
                    "version": 2,
                    "epoch": self.epoch,
                    "sequence": self.sequence,
                    "operation": operation,
                    "created_ns": time.monotonic_ns(),
                    **value,
                }
            )
            + b"\n"
        )
        if self.socket.send(payload) != len(payload):
            self.socket.shutdown(socket.SHUT_RDWR)
            raise model.ControlError(
                "partial follower command; channel revoked"
            )

    def read(self):
        """Cache only received executed state, preserving source progression."""
        for data in self.frames.receive(self.socket):
            value = json.loads(data)
            if (
                value.get("version") != 2
                or value["epoch"] != self.epoch
                or value["source"] != "isaac_kinematic"
            ):
                raise model.ControlError("follower source or ownership changed")
            self.feedback = kinematic.Feedback(
                tuple(value["q"]),
                tuple(value["qd"]),
                value["time_s"],
                time.monotonic_ns(),
                value["active"] and not value["fault"],
                value["fault"] or "Isaac owner is inactive",
                gripper_position=value["gripper_position"],
            )
        return self.feedback

    def move(self, q, speed, acceleration, gripper_position=None):
        """Start an asynchronous bounded kinematic route."""
        value = (
            {}
            if gripper_position is None
            else {"gripper_position": gripper_position}
        )
        self.send("move", q=q, speed=speed, acceleration=acceleration, **value)

    def servo(self, q, gripper_position=None):
        """Send one already-conditioned absolute joint target."""
        value = (
            {}
            if gripper_position is None
            else {"gripper_position": gripper_position}
        )
        self.send("servo", q=q, **value)

    def stop(self, _servo):
        """Stop at the executed pose; never request HOME."""
        if not self.closed:
            self.send("stop")

    def heartbeat(self):
        """Refresh ownership independently of operator motion."""
        now = time.monotonic()
        if now - self.last_heartbeat >= 0.1:
            self.send("heartbeat")
            self.last_heartbeat = now

    def close(self):
        """Close only this owner's channel; EOF also revokes execution."""
        if self.closed:
            return
        try:
            self.send("release")
        except OSError:
            pass
        finally:
            self.closed = True
            self.socket.close()


class Service:
    """Render-thread command acceptance with epoch, sequence and age checks."""

    def __init__(self, endpoint, limits, gripper_speed=255.0):
        self.endpoint = endpoint
        endpoint.parent.mkdir(parents=True, exist_ok=True)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.setblocking(False)
        # Never delete an existing socket: another service may own it.
        self.socket.bind(str(endpoint))
        self.socket.listen(1)
        self.engine = kinematic.Engine(limits, time.monotonic(), gripper_speed)
        self.epoch, self.peer, self.sequence = None, None, -1
        self.began = time.monotonic()
        self.frames = Frames()
        self.outgoing = b""

    def release(self):
        """Revoke execution and discard buffered commands from this owner."""
        self.engine.hold()
        self.engine.active = False
        if self.peer:
            self.peer.close()
        self.peer, self.epoch, self.sequence = None, None, -1
        self.frames = Frames()
        self.outgoing = b""

    def receive(self):
        """Accept ordered commands only from the currently connected owner."""
        if self.peer is None:
            try:
                self.peer, _ = self.socket.accept()
                self.peer.setblocking(False)
            except BlockingIOError:
                return
        try:
            for data in self.frames.receive(self.peer):
                value = command(data)
                age_limit = (
                    100_000_000
                    if value["operation"] == "servo"
                    else 500_000_000
                )
                if (
                    not 0
                    <= time.monotonic_ns() - value["created_ns"]
                    <= age_limit
                ):
                    continue
                if value["operation"] == "claim":
                    if self.epoch is not None:
                        continue
                    self.epoch = value["epoch"]
                if (
                    value["epoch"] != self.epoch
                    or value["sequence"] <= self.sequence
                ):
                    continue
                self.sequence = value["sequence"]
                self.engine.command(value["operation"], value, time.monotonic())
                if value["operation"] == "release":
                    self.release()
                    break
        except (EOFError, ConnectionError):
            self.release()
        except (ValueError, KeyError, TypeError, model.ControlError) as error:
            self.engine.fault = str(error)
            self.engine.hold()

    def publish(self):
        """Publish executed state only after scene application."""
        if self.peer is None or self.epoch is None:
            return
        if not self.outgoing:
            self.outgoing = (
                encode(
                    {
                        "version": 2,
                        "source": "isaac_kinematic",
                        "epoch": self.epoch,
                        "time_s": time.monotonic() - self.began,
                        "q": self.engine.q,
                        "qd": self.engine.qd,
                        "gripper_position": self.engine.gripper_position,
                        "active": self.engine.active,
                        "fault": self.engine.fault,
                    }
                )
                + b"\n"
            )
        try:
            sent = self.peer.send(self.outgoing)
            self.outgoing = self.outgoing[sent:]
        except ConnectionError:
            self.release()
        except BlockingIOError:
            pass  # Preserve one partial frame; never queue further readbacks.

    def close(self):
        """Remove only the endpoint bound by this service."""
        self.release()
        self.socket.close()
        self.endpoint.unlink(missing_ok=True)
