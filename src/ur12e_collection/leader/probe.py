"""Bounded read-only leader diagnostics with immutable raw evidence."""

import dataclasses
import json
import math
import pathlib
import platform
import time
from importlib import metadata

from ur12e_collection.leader.bus import IDS, ReadBus, ReadError

LAYOUTS = {"position": (132, 4), "motion": (128, 8), "full": (64, 83)}
# Address, byte width, signed. Keep raw units in reports.
REGISTERS = {
    "model": (0, 2, False),
    "firmware": (6, 1, False),
    "baud_register": (8, 1, False),
    "return_delay": (9, 1, False),
    "drive_mode": (10, 1, False),
    "operating_mode": (11, 1, False),
    "homing_offset": (20, 4, True),
    "pwm_limit": (36, 2, False),
    "max_position": (48, 4, False),
    "min_position": (52, 4, False),
    "shutdown": (63, 1, False),
    "torque": (64, 1, False),
    "hardware_error": (70, 1, False),
    "position_d_gain": (80, 2, False),
    "position_i_gain": (82, 2, False),
    "position_p_gain": (84, 2, False),
    "watchdog": (98, 1, True),
    "goal_pwm": (100, 2, True),
    "profile_acceleration": (108, 4, False),
    "profile_velocity": (112, 4, False),
    "goal_position": (116, 4, True),
    "moving": (122, 1, False),
    "moving_status": (123, 1, False),
    "present_pwm": (124, 2, True),
    "present_load": (126, 2, True),
    "velocity": (128, 4, True),
    "position": (132, 4, True),
    "position_trajectory": (140, 4, True),
    "voltage_deci_v": (144, 2, False),
    "temperature_c": (146, 1, False),
}


def inventory(bus: ReadBus) -> dict:
    """Inspect identities before using the XL430 control table."""
    motors = {}
    for motor in IDS:
        identity = bus.read(motor, 0, 64)
        if identity.integers(0, 2) != (1060,) or any(identity.errors):
            raise ReadError(f"ID{motor}: expected a responsive XL430")
        state = bus.read(motor, 64, 83)
        values = {}
        for name, (address, width, signed) in REGISTERS.items():
            block = identity if address < 64 else state
            values[name] = block.integers(address, width, signed=signed)[0]
        values["status_errors"] = list(state.errors)
        values["acquisition_start_ns"] = identity.start_ns
        values["acquisition_end_ns"] = state.end_ns
        motors[str(motor)] = values
    return motors


def distribution(values: list[float]) -> dict:
    """Nearest-rank percentiles; no optional numeric library needed."""
    ordered = sorted(values)
    if not ordered:
        return {}
    return {
        **{
            f"p{p}": ordered[max(0, math.ceil(len(ordered) * p / 100) - 1)]
            for p in (50, 95, 99)
        },
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
    }


@dataclasses.dataclass
class Timing:
    """Retain partial timing evidence even when a later transaction fails."""

    costs: list = dataclasses.field(default_factory=list)
    gaps: list = dataclasses.field(default_factory=list)
    first: int | None = None
    previous: int | None = None
    end: int | None = None

    def add(self, block: object) -> None:
        """Measure an acquisition interval and consecutive request starts."""
        if self.first is None:
            self.first = block.start_ns
        if self.previous is not None:
            self.gaps.append((block.start_ns - self.previous) / 1e6)
        self.previous, self.end = block.start_ns, block.end_ns
        self.costs.append((self.end - self.previous) / 1e6)

    def report(self) -> dict:
        """Do not infer latency from the requested polling rate."""
        return {
            "samples": len(self.costs),
            "acquisition_ms": distribution(self.costs),
            "start_gap_ms": distribution(self.gaps),
            "sample_hz": (
                len(self.costs) * 1e9 / (self.end - self.first)
                if self.costs and self.end > self.first
                else None
            ),
        }


def run(
    device: str,
    baudrate: int,
    seconds: float,
    layout: str,
    output: pathlib.Path,
    *,
    fast: bool = False,
) -> dict:
    """Record one explicit read experiment; never claim control readiness."""
    # The explicit connection, acquisition and output arguments are independent.
    # pylint: disable=too-many-arguments,too-many-locals
    if not math.isfinite(seconds) or not 0 <= seconds <= 300:
        raise ValueError("probe duration must be between 0 and 300 seconds")
    address, size = LAYOUTS[layout]
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "state": "failed",
        "motion_ready": False,
        "motor_writes": False,
        "device": device,
        "baudrate": baudrate,
        "layout": layout,
        "fast_sync": fast,
        "requested_seconds": seconds,
        "clock": "host_monotonic_acquisition_interval",
        "platform": platform.platform(),
        "dependencies": {
            name: metadata.version(name)
            for name in ("dynamixel-sdk", "pyserial")
        },
    }
    timing = Timing()
    bus = None
    try:
        with (output / "samples.jsonl").open("x", encoding="utf-8") as trace:
            with ReadBus(device, baudrate) as bus:
                result["before"] = inventory(bus)
                if fast and any(
                    m["firmware"] < 45 for m in result["before"].values()
                ):
                    raise ReadError("fast sync requires XL430 firmware >=45")
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    block = bus.sync(address, size, fast=fast)
                    timing.add(block)
                    row = dataclasses.asdict(block)
                    row["values"] = [v.hex() for v in block.values]
                    row["sequence"] = len(timing.costs) - 1
                    row["position"] = block.integers(132, 4, signed=True)
                    trace.write(json.dumps(row) + "\n")
                    if any(block.errors):
                        raise ReadError(f"motor status error: {block.errors}")
                result["after"] = inventory(bus)
                result["state"] = "completed"
    except (OSError, RuntimeError, KeyboardInterrupt) as error:
        result["error"] = str(error) or type(error).__name__
    finally:
        result["traffic"] = bus.traffic() if bus is not None else {}
        result.update(timing.report())
        (output / "report.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    return result
