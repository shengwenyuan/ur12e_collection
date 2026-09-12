"""Backend-neutral simulated feedback and gripper command coordinates."""

import dataclasses
import math

from ur12e_collection.control import model


def gripper_position(value):
    """Validate simulated command coordinates, never a device register."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 255
    ):
        raise model.ControlError("invalid simulated gripper position")
    return value


@dataclasses.dataclass(frozen=True)
class Feedback:
    """Executed simulated joints; never fabricate UR safety/program codes."""

    # One immutable arm/tool feedback record.
    # pylint: disable=too-many-instance-attributes

    q: tuple
    qd: tuple
    timestamp: float
    received_ns: int
    motion_allowed: bool
    motion_error: str
    source_clock: str = "isaac_kinematic_monotonic"
    gripper_position: float = 0.0
    gripper_open: bool | None = None
    finger_positions_m: tuple = ()
    finger_velocities_m_s: tuple = ()

    def __post_init__(self):
        model.joints(self.q)
        model.joints(self.qd)
        gripper_position(self.gripper_position)
        if self.gripper_open is None:
            object.__setattr__(self, "gripper_open", self.gripper_position == 0)
        if not isinstance(self.gripper_open, bool):
            raise model.ControlError("invalid simulated gripper readiness")
        if self.source_clock == "isaac_physics_simulation":
            for values in (self.finger_positions_m, self.finger_velocities_m_s):
                if len(values) != 2 or any(
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                    for v in values
                ):
                    raise model.ControlError("invalid physical jaw feedback")
        if not isinstance(self.motion_allowed, bool) or not isinstance(
            self.motion_error, str
        ):
            raise model.ControlError("invalid simulated health")
        if (
            not isinstance(self.received_ns, int)
            or isinstance(self.received_ns, bool)
            or self.received_ns < 0
        ):
            raise model.ControlError("invalid simulated receipt time")
        if (
            not isinstance(self.timestamp, (int, float))
            or isinstance(self.timestamp, bool)
            or not math.isfinite(self.timestamp)
            or self.timestamp < 0
        ):
            raise model.ControlError("invalid simulated source time")

    @property
    def holding_allowed(self):
        """Simulation has no separately running UR program."""
        return self.motion_allowed and not any(self.qd)
