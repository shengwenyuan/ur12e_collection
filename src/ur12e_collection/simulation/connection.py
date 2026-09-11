"""Local URSim authorization, separate from reusable UR commands."""

import contextlib
import fcntl
import json
import pathlib
import socket
import time

from ur12e_collection import ur, wire
from ur12e_collection.control.model import ControlError
from ur12e_collection.control.ur import URTransport, read_state
from ur12e_collection.control.program import NativeHome
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
        "running",
        "load /ursim/programs/collector_ready.urp",
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


def _initialize(address: str) -> None:
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


class Station:
    """One simulator lease and readback, with explicit program ownership."""

    def __init__(self, address: str, receiver):
        self.address, self.receiver = address, receiver
        self.owner = None

    def read(self):
        """Observe the arm while no motion program is owned."""
        return read_state(self.receiver)

    def _acquire(self, owner: str) -> None:
        if self.owner is not None:
            raise ControlError("another program already owns this connection")
        self.owner = owner

    @contextlib.contextmanager
    def home(self):
        """Yield native HOME only after the SDK owner has fully released it."""
        permit = json.loads(
            pathlib.Path("/sim-permit.json").read_text(encoding="utf-8")
        )
        home = permit.get("home")
        if (
            not isinstance(home, dict)
            or home.get("program") != "/ursim/programs/collector_ready.urp"
        ):
            raise ControlError(
                "native HOME launch configuration is not verified"
            )
        if max(abs(a - b) for a, b in zip(home["q"], profile.HOME)) > 1e-6:
            raise ControlError("native HOME launch target differs")
        self._acquire("home")
        program = NativeHome(
            lambda cmd: dashboard(self.address, cmd),
            lambda: read_state(self.receiver),
            profile.LIMITS,
            "/ursim/programs/collector_ready.urp",
        )
        try:
            yield program
        finally:
            try:
                program.close()
            finally:
                self.owner = None

    @contextlib.contextmanager
    def motion(self):
        """Upload an idle SDK program on explicit ownership acquisition."""
        self._acquire("rtde")
        control = transport = None
        try:
            _identity(self.address)
            if dashboard(self.address, "running") != "Program running: false":
                raise ControlError("another native program is running")
            state = read_state(self.receiver)
            if state.runtime_state != 1 or max(map(abs, state.qd)) >= 0.01:
                raise ControlError("SDK handover requires measured standstill")
            # pylint: disable=import-outside-toplevel,import-error
            import rtde_control

            control = rtde_control.RTDEControlInterface(
                self.address,
                float(profile.COMMAND_HZ),
                rtde_control.RTDEControlInterface.FLAG_UPLOAD_SCRIPT
                | rtde_control.RTDEControlInterface.FLAG_UPPER_RANGE_REGISTERS,
            )
            if not control.setWatchdog(5.0):
                raise ControlError("simulator watchdog setup failed")
            transport = URTransport(
                control, self.receiver, profile.PERIOD, owns_receiver=False
            )
            yield transport
        finally:
            try:
                if transport is not None:
                    transport.close()
                elif control is not None:
                    try:
                        control.stopScript()
                    finally:
                        control.disconnect()
            finally:
                self.owner = None


@contextlib.contextmanager
def open_station():
    """Authorize one local peer before initialization or SDK creation."""
    lease = Lease(pathlib.Path("/sim-lock/controller.lock"))
    receiver = None
    try:
        address = verify_boundary()
        _initialize(address)
        # pylint: disable=import-outside-toplevel,import-error
        import rtde_receive

        receiver = rtde_receive.RTDEReceiveInterface(
            address,
            float(profile.FEEDBACK_HZ),
            ur.OUTPUT_FIELDS + ["runtime_state"],
        )
        yield Station(address, receiver)
    finally:
        try:
            if receiver is not None:
                receiver.disconnect()
        finally:
            lease.close()


@contextlib.contextmanager
def open_controller():
    """Compatibility entrypoint for a single explicit SDK ownership interval."""
    with open_station() as station:
        with station.motion() as transport:
            yield transport
