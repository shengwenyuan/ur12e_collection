"""M10 contracts: leader intent, issued commands, and feedback stay distinct."""

import dataclasses
import math

SCHEMA_VERSION = 1
CAMERA_ROLES = ("wrist", "third_left", "third_right")
JOINT_NAMES = (
    "shoulder_pan_joint",
    "shoulder_lift_joint",
    "elbow_joint",
    "wrist_1_joint",
    "wrist_2_joint",
    "wrist_3_joint",
)


def _nonnegative_integer(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _joints(values: tuple[float, ...] | None) -> None:
    if values is None:
        return
    if not isinstance(values, tuple) or len(values) != 6:
        raise ValueError("joint positions must be an immutable six-value tuple")
    if any(
        not isinstance(v, (int, float))
        or isinstance(v, bool)
        or not math.isfinite(v)
        for v in values
    ):
        raise ValueError("joint positions must be finite radians")


def _raw(value: int | None) -> None:
    if value is not None and (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= 255
    ):
        raise ValueError(
            "Robotiq raw position must be an integer from 0 to 255"
        )


@dataclasses.dataclass(frozen=True)
class SampleTime:
    """Keep acquisition and host receipt clocks separate; unknown is None."""

    source_ns: int | None
    source_clock: str
    received_monotonic_ns: int

    def __post_init__(self) -> None:
        if self.source_ns is not None:
            _nonnegative_integer(self.source_ns, "source_ns")
        if not isinstance(self.source_clock, str) or not self.source_clock:
            raise ValueError("source clock domain must be explicit")
        _nonnegative_integer(self.received_monotonic_ns, "receipt timestamp")


@dataclasses.dataclass(frozen=True)
class Provenance:
    """Identify the source and distinguish fixtures from physical data."""

    source_id: str
    sequence: int
    time: SampleTime
    simulated: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or not self.source_id
            or not isinstance(self.time, SampleTime)
        ):
            raise ValueError("source identity and SampleTime are required")
        _nonnegative_integer(self.sequence, "sequence")
        if not isinstance(self.simulated, bool):
            raise ValueError("simulated must be explicit boolean provenance")


@dataclasses.dataclass(frozen=True)
class LeaderIntent:
    """Mapped operator intent, before control constraints; gripper is raw."""

    provenance: Provenance
    joint_positions_rad: tuple[float, ...] | None
    gripper_request_raw: int | None

    kind: str = dataclasses.field(default="leader_intent", init=False)
    schema_version: int = dataclasses.field(default=SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, Provenance):
            raise ValueError("sample provenance is required")
        _joints(self.joint_positions_rad)
        _raw(self.gripper_request_raw)


@dataclasses.dataclass(frozen=True)
class SentCommand:
    """Only a command actually issued by the future exclusive controller."""

    provenance: Provenance
    joint_positions_rad: tuple[float, ...]
    gripper_request_raw: int | None

    kind: str = dataclasses.field(default="sent_command", init=False)
    schema_version: int = dataclasses.field(default=SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        if self.joint_positions_rad is None:
            raise ValueError("a sent joint command cannot have missing targets")
        if not isinstance(self.provenance, Provenance):
            raise ValueError("sample provenance is required")
        _joints(self.joint_positions_rad)
        _raw(self.gripper_request_raw)


@dataclasses.dataclass(frozen=True)
class FollowerState:
    """Measured positions; never replace missing feedback with a goal."""

    provenance: Provenance
    joint_positions_rad: tuple[float, ...] | None
    gripper_position_raw: int | None

    kind: str = dataclasses.field(default="follower_state", init=False)
    schema_version: int = dataclasses.field(default=SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, Provenance):
            raise ValueError("sample provenance is required")
        _joints(self.joint_positions_rad)
        _raw(self.gripper_position_raw)
