"""Physical execution boundary; drive requests never stand in for readback."""

import dataclasses
import math
from typing import Protocol

from ur12e_collection.control import model
from ur12e_collection.followers import kinematic

# Exact numeric types exclude boolean configuration values.
# pylint: disable=unidiomatic-typecheck


@dataclasses.dataclass(frozen=True)
class Settings:  # pylint: disable=too-many-instance-attributes
    """Explicit provisional simulation settings, unrelated to real UR limits."""

    step_hz: int
    arm_stiffness: tuple
    arm_damping: tuple
    arm_effort: tuple
    finger_stiffness: float
    finger_damping: float
    finger_effort: float
    static_friction: float
    dynamic_friction: float
    restitution: float
    open_tolerance_m: float
    finger_stopped_speed_m_s: float

    def __post_init__(self):
        if type(self.step_hz) is not int or not 120 <= self.step_hz <= 1000:
            raise ValueError(
                "physics step_hz must be an integer in [120, 1000]"
            )
        for name in ("arm_stiffness", "arm_damping", "arm_effort"):
            values = getattr(self, name)
            if len(values) != 6:
                raise ValueError(f"{name} requires six joint-ordered values")
            for value in values:
                positive(value)
            object.__setattr__(self, name, tuple(values))
        for name in (
            "finger_stiffness",
            "finger_damping",
            "finger_effort",
            "static_friction",
            "dynamic_friction",
            "open_tolerance_m",
            "finger_stopped_speed_m_s",
        ):
            positive(getattr(self, name))
        if (
            type(self.restitution) not in (int, float)
            or not 0 <= self.restitution <= 1
            or self.dynamic_friction > self.static_friction
            or self.open_tolerance_m > 0.001
        ):
            raise ValueError("invalid physical material or opening tolerance")


def positive(value: float) -> None:
    """Reject booleans, nonfinite values and nonpositive parameters."""
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("physics parameters must be positive finite numbers")


@dataclasses.dataclass(frozen=True)
class Sample:
    """One actual solver sample in radians, meters and simulation seconds."""

    q: tuple
    qd: tuple
    fingers: tuple
    finger_velocities: tuple
    time_s: float
    sequence: int
    acquired_ns: int

    def __post_init__(self):
        model.joints(self.q)
        model.joints(self.qd)
        for values in (self.fingers, self.finger_velocities):
            if len(values) != 2 or any(
                type(v) not in (int, float) or not math.isfinite(v)
                for v in values
            ):
                raise model.ControlError("invalid physical finger readback")
        if (
            type(self.time_s) not in (int, float)
            or not math.isfinite(self.time_s)
            or self.time_s < 0
        ):
            raise model.ControlError("invalid physics simulation time")
        if (
            type(self.sequence) is not int
            or self.sequence < 0
            or type(self.acquired_ns) is not int
            or self.acquired_ns < 0
        ):
            raise model.ControlError("invalid physics sample clock")


class Solver(Protocol):
    """Scene execution returns measurements without hardware handles."""

    def read(self) -> Sample:
        """Return the last acquisition without advancing its clock."""

    def step(self, q: tuple, fingers: tuple) -> Sample:
        """Drive one fixed step and return the resulting joint state."""


class Engine:
    """Share target planning with kinematics; own independent measured state."""

    source = "isaac_physics"

    def __init__(
        self,
        limits: model.Limits,
        now: float,
        driver: Solver,
        settings: Settings,
        gripper_speed: float = 255.0,
    ):
        self.driver, self.settings = driver, settings
        self.sample = driver.read()
        self.planner = kinematic.Engine(limits, now, gripper_speed)
        self.heartbeat_at = now
        self.invalidated = False
        self.holding_fingers = self.sample.fingers
        self.hold()

    @property
    def active(self):
        """Whether the shared target planner has an owner."""
        return self.planner.active

    @active.setter
    def active(self, value):
        self.planner.active = value

    @property
    def fault(self):
        """Latched execution or ownership fault."""
        return self.planner.fault

    @fault.setter
    def fault(self, value):
        self.planner.fault = value

    @property
    def q(self):
        """Last solver positions in radians."""
        return self.sample.q

    @property
    def qd(self):
        """Last solver velocities in radians per second."""
        return self.sample.qd

    @property
    def gripper_position(self):
        """Compatibility closure derived from actual aperture, never intent."""
        return max(0.0, min(255.0, 255 * (1 - sum(self.sample.fingers) / 0.05)))

    def hold(self) -> None:
        """Latch measured arm and jaw targets; preserve feedback."""
        self.planner.q = self.q
        self.planner.gripper_position = self.gripper_position
        self.planner.hold()
        self.holding_fingers = self.sample.fingers

    def invalidate(self, reason: str) -> None:
        """A paused/reset solver requires application restart."""
        self.hold()
        self.fault = reason
        self.invalidated = True

    def command(self, operation: str, value: dict, now: float) -> None:
        """Start at measured state; stop preserves residual speed."""
        if self.invalidated:
            raise model.ControlError(self.fault)
        if operation in ("claim", "move", "stop", "release"):
            self.hold()
        # Target profiles use solver time; ownership expiry uses host time.
        self.planner.command(operation, value, self.planner.previous)
        self.heartbeat_at = now
        if operation in ("servo", "move"):
            self.holding_fingers = None

    def update(self, now: float) -> tuple:
        """Apply one fixed solver step and accept only progressing readback."""
        if self.invalidated:
            return self.q
        if self.active and not self.fault and now - self.heartbeat_at > 0.5:
            self.hold()
            self.fault = "physical owner heartbeat expired"
        target = self.planner.advance_targets(
            self.planner.previous + 1 / self.settings.step_hz
        )
        fingers = self.holding_fingers
        if fingers is None:
            fingers = (0.025 * (1 - self.planner.gripper_position / 255),) * 2
        try:
            sample = self.driver.step(target, fingers)
            if (
                sample.time_s <= self.sample.time_s
                or sample.sequence <= self.sample.sequence
                or sample.acquired_ns <= self.sample.acquired_ns
            ):
                raise model.ControlError("physics clock stopped or reset")
            self.sample = sample
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.invalidate(str(error))
            raise model.ControlError(str(error)) from error
        return self.q

    def snapshot(self, _now: float) -> dict:
        """Publish raw jaws and solver provenance alongside derived closure."""
        sample = self.sample
        opened = all(
            abs(q - 0.025) <= self.settings.open_tolerance_m
            for q in sample.fingers
        ) and all(
            abs(v) <= self.settings.finger_stopped_speed_m_s
            for v in sample.finger_velocities
        )
        return {
            "source": self.source,
            "requested_q": self.planner.target,
            "planned_q": self.planner.q,
            "requested_gripper_position": self.planner.gripper_target,
            "time_s": sample.time_s,
            "sequence": sample.sequence,
            "acquired_ns": sample.acquired_ns,
            "q": sample.q,
            "qd": sample.qd,
            "finger_positions_m": sample.fingers,
            "finger_velocities_m_s": sample.finger_velocities,
            "gripper_aperture_m": sum(sample.fingers),
            "gripper_position": self.gripper_position,
            "gripper_open": opened,
            "active": self.active,
            "fault": self.fault,
        }
