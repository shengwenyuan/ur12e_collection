"""Explicit, journaled baud maintenance; normal diagnostics remain read-only."""

import argparse
import hashlib
import json
import os
import pathlib

from ur12e_collection import filesystem
from ur12e_collection.leader import bus, probe

RATES = {57600: 1, 1000000: 3, 3000000: 5}
TRANSITIONS = {(57600, 1000000), (1000000, 3000000)}
SETTINGS = (
    "model",
    "firmware",
    "return_delay",
    "drive_mode",
    "operating_mode",
    "homing_offset",
    "pwm_limit",
    "max_position",
    "min_position",
    "shutdown",
    "torque",
    "position_d_gain",
    "position_i_gain",
    "position_p_gain",
    "watchdog",
    "goal_pwm",
    "profile_acceleration",
    "profile_velocity",
)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


class _BaudPort(bus.ReadPort):
    """A single armed, addressed Baud Rate write is the only write exception."""

    permit = None

    def writePort(self, packet):  # pylint: disable=invalid-name
        if len(packet) > 7 and packet[7] == 3:
            allowed = self.permit
            self.permit = None
            if allowed is None:
                raise bus.ReadError("no Baud Rate write is armed")
            expected = b"\xff\xff\xfd\x00" + bytes(
                (allowed[0], 6, 0, 3, 8, 0, allowed[1])
            )
            if len(packet) != 13 or bytes(packet[:11]) != expected:
                raise bus.ReadError("only the armed Baud Rate write is allowed")
            self.instructions[3] += 1
            return self.ser.write(packet)
        return super().writePort(packet)


class MaintenanceBus(bus.ReadBus):
    """Maintain exclusive serial ownership across known host baud switches."""

    _port_type = _BaudPort

    def host_baud(self, rate: int) -> None:
        """Change only the host serial speed, without releasing ownership."""
        if rate not in RATES:
            raise ValueError("unsupported maintenance baudrate")
        self._port.ser.baudrate = rate
        self._port.baudrate = rate
        self._port.tx_time_per_byte = 10_000 / rate
        self._port.ser.reset_input_buffer()
        self._port.is_using = False

    def write_baud(self, motor: int, value: int) -> str | None:
        """Emit one guarded EEPROM write; readback must resolve a lost ACK."""
        if (
            isinstance(motor, bool)
            or isinstance(value, bool)
            or motor not in bus.IDS
            or value not in RATES.values()
        ):
            raise ValueError("invalid baud write identity/value")
        torque = self.read(motor, 64, 1)
        if torque.errors != (0,) or torque.integers(64, 1) != (0,):
            raise bus.ReadError("baud maintenance requires torque off")
        self._port.permit = (motor, value)
        try:
            result, error = self._packet.write1ByteTxRx(
                self._port, motor, 8, value
            )
            if error:
                raise bus.ReadError(f"baud write status error: {error}")
            return self._packet.getTxRxResult(result) if result else None
        finally:
            self._port.permit = None


def _checked_inventory(link, rate):
    values = probe.inventory(link)
    if any(
        m["baud_register"] != RATES[rate]
        or m["torque"] != 0
        or m["hardware_error"] != 0
        or any(m["status_errors"])
        for m in values.values()
    ):
        raise bus.ReadError("inconsistent baud, torque or motor fault")
    return values


def _same_settings(before, after):
    if any(
        before[motor][key] != after[motor][key]
        for motor in before
        for key in SETTINGS
    ):
        raise bus.ReadError("motor configuration changed since preparation")
    for motor, old in before.items():
        new = after[motor]
        # Observed torque-off goals can follow encoder changes. Keep both raw
        # values; require each goal to equal its concurrent position.
        if old["goal_position"] != new["goal_position"] and not all(
            state["torque"] == 0 and state["goal_position"] == state["position"]
            for state in (old, new)
        ):
            raise bus.ReadError("goal changed independently of torque-off pose")


def prepare(
    device: str,
    output: pathlib.Path,
    *,
    from_baud: int = 57600,
    to_baud: int = 1000000,
) -> dict:
    """Read the old bus and test host baud support; never arm a motor write."""
    if (from_baud, to_baud) not in TRANSITIONS:
        raise ValueError("unsupported baud transition")
    if output.exists():
        raise FileExistsError(output)
    with MaintenanceBus(device, from_baud) as link:
        before = _checked_inventory(link, from_baud)
        link.host_baud(to_baud)
        link.host_baud(from_baud)
        after = _checked_inventory(link, from_baud)
        _same_settings(before, after)
        value = {
            "schema_version": 1,
            "device": device,
            "from_baud": from_baud,
            "to_baud": to_baud,
            "before": after,
            "traffic": link.traffic(),
        }
    value["plan_sha256"] = _digest(value)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    return value


def _plan(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "device",
        "from_baud",
        "to_baud",
        "before",
        "traffic",
        "plan_sha256",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("invalid maintenance plan")
    digest = value.pop("plan_sha256")
    if (
        _digest(value) != digest
        or value["schema_version"] != 1
        or (value["from_baud"], value["to_baud"]) not in TRANSITIONS
        or set(value["before"]) != {str(i) for i in bus.IDS}
    ):
        raise ValueError("maintenance plan differs from prepared operation")
    value["plan_sha256"] = digest
    return value


def _event(stream, name, **values):
    stream.write(json.dumps({"event": name, **values}) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _confirm_motor(link, motor, firmware, rate):
    identity = link.read(motor, 0, 10)
    torque = link.read(motor, 64, 1)
    observed = tuple(
        identity.integers(address, width)[0]
        for address, width in ((0, 2), (6, 1), (7, 1), (8, 1))
    )
    if (
        any(identity.errors)
        or any(torque.errors)
        or observed != (1060, firmware, motor, RATES[rate])
        or torque.integers(64, 1) != (0,)
    ):
        raise bus.ReadError(f"ID{motor}: new-rate verification failed")


def classify(link, rates=(57600, 1000000)) -> dict:
    """Locate every expected ID at only the two known rates, without writes."""
    found = {str(m): [] for m in bus.IDS}
    for rate in rates:
        register = RATES[rate]
        link.host_baud(rate)
        for motor in bus.IDS:
            try:
                block = link.read(motor, 0, 10)
                if (
                    not any(block.errors)
                    and block.integers(0, 2) == (1060,)
                    and block.integers(8, 1) == (register,)
                ):
                    found[str(motor)].append(rate)
            except (OSError, bus.ReadError):
                continue
    return found


def _migrate(link, planned, journal):
    source, target = planned["from_baud"], planned["to_baud"]
    before = _checked_inventory(link, source)
    _event(journal, "preflight", before=before)
    _same_settings(planned["before"], before)
    for motor in bus.IDS:
        link.host_baud(source)
        _event(
            journal, "write_intent", motor=motor, address=8, value=RATES[target]
        )
        ack = link.write_baud(motor, RATES[target])
        _event(journal, "write_result", motor=motor, ack_error=ack)
        link.host_baud(target)
        _confirm_motor(link, motor, before[str(motor)]["firmware"], target)
        _event(journal, "verified", motor=motor, baudrate=target)
    after = _checked_inventory(link, target)
    _same_settings(before, after)
    return after


def apply(plan: pathlib.Path, output: pathlib.Path, *, confirmed=False) -> dict:
    """Apply a reviewed plan only after explicit operator authorization."""
    if confirmed is not True:
        raise ValueError("explicit baud-write confirmation required")
    planned = _plan(plan)
    source, target = planned["from_baud"], planned["to_baud"]
    output.mkdir(parents=True, exist_ok=False)
    result = {"state": "failed", "motion_ready": False, "plan": planned}
    with (output / "journal.jsonl").open("x", encoding="utf-8") as journal:
        filesystem.sync(output)
        filesystem.sync(output.parent)
        try:
            with MaintenanceBus(planned["device"], source) as link:
                try:
                    result["after"] = _migrate(link, planned, journal)
                except (OSError, RuntimeError, KeyboardInterrupt) as error:
                    _event(journal, "failed", reason=str(error))
                    result["classification"] = classify(link, (source, target))
                    raise
                finally:
                    result["traffic"] = link.traffic()
            # Explicitly reopen once at the final baud; never emit more writes.
            with bus.ReadBus(planned["device"], target) as reader:
                reopened = _checked_inventory(reader, target)
                _same_settings(result["after"], reopened)
            connection = {
                "device": planned["device"],
                "baudrate": target,
            }
            _event(journal, "completed", connection=connection)
            result.update(state="completed", connection=connection)
        except (OSError, RuntimeError, KeyboardInterrupt) as error:
            result["error"] = str(error) or type(error).__name__
    (output / "report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main(argv=None) -> int:
    """Keep maintenance separate from the collection/diagnostic entrypoints."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    draft = commands.add_parser("prepare", help="read-only preparation")
    draft.add_argument("--port", required=True)
    draft.add_argument("--from-baud", type=int, choices=RATES, default=57600)
    draft.add_argument("--to-baud", type=int, choices=RATES, default=1000000)
    draft.add_argument("--output", type=pathlib.Path, required=True)
    change = commands.add_parser("apply", help="explicit EEPROM baud writes")
    change.add_argument("--plan", type=pathlib.Path, required=True)
    change.add_argument("--output", type=pathlib.Path, required=True)
    change.add_argument(
        "--confirm-baud-write", action="store_true", required=True
    )
    args = parser.parse_args(argv)
    if args.operation == "prepare":
        value = prepare(
            args.port,
            args.output,
            from_baud=args.from_baud,
            to_baud=args.to_baud,
        )
    else:
        value = apply(args.plan, args.output, confirmed=args.confirm_baud_write)
    print(json.dumps(value, indent=2))
    return 0 if value.get("state", "completed") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
