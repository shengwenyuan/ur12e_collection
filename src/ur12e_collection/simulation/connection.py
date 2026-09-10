"""Local URSim authorization, separate from reusable UR commands."""

import contextlib
import fcntl
import json
import pathlib
import socket
import time

from ur12e_collection import wire
from ur12e_collection.control.model import ControlError
from ur12e_collection.control.ur import URTransport
from ur12e_collection.simulation import profile


class Lease:
    """Exclusive lock shared across client processes and containers."""

    def __init__(self, path: pathlib.Path):
        self.stream = path.open("a", encoding="utf-8")
        try:
            fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise ControlError(
                "another controller already owns URSim"
            ) from error

    def close(self) -> None:
        """Release ownership without removing the shared lock inode."""
        self.stream.close()


def verify_boundary() -> str:
    """Require an inspected local peer and no external route."""
    permit = json.loads(
        pathlib.Path("/sim-permit.json").read_text(encoding="utf-8")
    )
    if (
        permit.get("image") != profile.IMAGE
        or permit.get("host") != profile.HOST
    ):
        raise ControlError("invalid simulator launch permit")
    routes = pathlib.Path("/proc/net/route").read_text(encoding="utf-8")
    if any(line.split()[1] == "00000000" for line in routes.splitlines()[1:]):
        raise ControlError("simulator client must not have an external route")
    ipv6 = pathlib.Path("/proc/net/ipv6_route")
    if ipv6.exists():
        for line in ipv6.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if fields[:2] == ["0" * 32, "00"] and fields[-1] != "lo":
                raise ControlError("simulator client has an IPv6 default route")
    address = socket.gethostbyname(profile.HOST)
    if address != permit.get("address"):
        raise ControlError("simulator peer differs from inspected container")
    return address


def dashboard(address: str, command: str) -> str:
    """Bound one command to the already-verified simulator peer."""
    allowed = {
        "PolyscopeVersion",
        "get serial number",
        "is in remote control",
        "safetystatus",
        "robotmode",
        "power on",
        "brake release",
        "load /ursim/programs/ready.urp",
        "play",
        "stop",
    }
    if command not in allowed:
        raise ControlError("unsupported simulator Dashboard operation")
    with socket.create_connection((address, 29999), timeout=2) as conn:
        deadline = time.monotonic_ns() + 2_000_000_000
        if not wire.line(conn, deadline, 512).startswith(b"Connected:"):
            raise ControlError("unexpected simulator Dashboard greeting")
        conn.sendall((command + "\n").encode("ascii"))
        return wire.line(conn, deadline, 512).decode("ascii").strip()


def _identity(address: str) -> None:
    if dashboard(address, "get serial number") != profile.SERIAL:
        raise ControlError("simulator serial mismatch")
    if not dashboard(address, "PolyscopeVersion").startswith(profile.VERSION):
        raise ControlError("simulator version mismatch")
    if dashboard(address, "is in remote control") != "true":
        raise ControlError("select Remote Control in the local URSim pendant")
    if dashboard(address, "safetystatus") != "Safetystatus: NORMAL":
        raise ControlError(
            "simulator safety is not normal; explicit recovery required"
        )


def _wait_mode(address: str, expected: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if dashboard(address, "robotmode") == "Robotmode: " + expected:
            return
        time.sleep(0.1)
    raise ControlError("simulator initialization timed out")


@contextlib.contextmanager
def open_controller():
    """Authorize once, then yield the shared SDK adapter."""
    lease = Lease(pathlib.Path("/sim-lock/controller.lock"))
    receiver = control = transport = None
    try:
        address = verify_boundary()
        _identity(address)
        mode = dashboard(address, "robotmode")
        if mode == "Robotmode: POWER_OFF":
            if dashboard(address, "power on") != "Powering on":
                raise ControlError("simulator power-on rejected")
            _wait_mode(address, "IDLE")
            mode = "Robotmode: IDLE"
        if mode == "Robotmode: IDLE":
            if dashboard(address, "brake release") != "Brake releasing":
                raise ControlError("simulator brake release rejected")
            _wait_mode(address, "RUNNING")
        elif mode != "Robotmode: RUNNING":
            raise ControlError("simulator is not in an initializable mode")
        # Only this authorized factory imports a command-capable SDK.
        # pylint: disable=import-outside-toplevel,import-error
        import rtde_control
        import rtde_receive

        receiver = rtde_receive.RTDEReceiveInterface(
            address,
            125.0,
            [
                "timestamp",
                "actual_q",
                "actual_qd",
                "robot_mode",
                "safety_mode",
                "runtime_state",
            ],
        )
        control = rtde_control.RTDEControlInterface(
            address,
            50.0,
            rtde_control.RTDEControlInterface.FLAG_UPLOAD_SCRIPT
            | rtde_control.RTDEControlInterface.FLAG_UPPER_RANGE_REGISTERS,
        )
        if not control.setWatchdog(5.0):
            raise ControlError("simulator watchdog setup failed")
        transport = URTransport(control, receiver, profile.PERIOD)
        yield transport
    finally:
        try:
            if transport is not None:
                transport.close()
            else:
                if control is not None:
                    control.disconnect()
                if receiver is not None:
                    receiver.disconnect()
        finally:
            lease.close()
