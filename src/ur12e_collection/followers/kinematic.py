"""Deterministic joint-space execution, explicitly without physical dynamics."""

import math

from ur12e_collection.control import model
from ur12e_collection.followers.state import gripper_position


class Engine:
    """Execute latest targets and bounded HOME at render updates."""

    # One owner retains joint, gripper and watchdog execution state together.
    # pylint: disable=too-many-instance-attributes

    source = "isaac_kinematic"

    def __init__(self, limits, now: float, gripper_speed=255.0):
        if not math.isfinite(gripper_speed) or gripper_speed <= 0:
            raise model.ControlError("invalid simulated gripper speed")
        self.limits = limits
        self.gripper_speed = gripper_speed
        self.gripper_position = self.gripper_target = 0.0
        self.q, self.qd = limits.ready, (0.0,) * 6
        self.target = self.q
        self.route = None
        self.previous = self.heartbeat_at = now
        self.began = now
        self.sequence = 0
        self.active = False
        self.fault = None

    def command(self, operation: str, value: dict, now: float):
        """Apply owner commands; faults require a new ownership epoch."""
        if operation == "claim":
            self.active, self.fault = True, None
            self.heartbeat_at = now
            return
        if not self.active or self.fault:
            raise model.ControlError("kinematic follower has no healthy owner")
        if operation in ("servo", "move"):
            target = tuple(value["q"])
            self.limits.check(target)
            gripper = gripper_position(
                value.get("gripper_position", self.gripper_target)
            )
            self.gripper_target = gripper
            self.target = target
            self.route = None
            if operation == "move":
                speed, acceleration = value["speed"], value["acceleration"]
                if not (
                    0 < speed <= self.limits.speed
                    and 0 < acceleration <= self.limits.acceleration
                ):
                    raise model.ControlError("invalid kinematic route limits")
                delta = model.distance(self.q, target)
                # Quintic blend has max first/second derivatives 1.875/5.774.
                duration = max(
                    0.001,
                    1.875 * delta / speed,
                    math.sqrt(5.774 * delta / acceleration),
                )
                self.route = (self.q, target, now, duration)
        elif operation in ("stop", "release"):
            self.hold()
            if operation == "release":
                self.active = False
        elif operation != "heartbeat":
            raise model.ControlError("unknown follower operation")
        self.heartbeat_at = now

    def hold(self):
        """Freeze kinematic state; this makes no physical braking claim."""
        self.target = self.q
        self.gripper_target = self.gripper_position
        self.route = None
        self.qd = (0.0,) * 6

    def update(self, now: float):
        """Publish only the state executed by this simulation update."""
        if self.active and now - self.heartbeat_at > 0.5:
            self.fault = "kinematic owner heartbeat expired"
            self.hold()
        return self.advance_targets(now)

    def advance_targets(self, now: float):
        """Advance bounded targets; physical execution owns its own watchdog."""
        previous = self.q
        dt = max(0, now - self.previous)
        if self.active and not self.fault:
            change = self.gripper_target - self.gripper_position
            maximum = self.gripper_speed * dt
            self.gripper_position += max(-maximum, min(maximum, change))
            if self.route:
                start, target, began, duration = self.route
                u = min(1.0, max(0.0, (now - began) / duration))
                blend = u**3 * (10 + u * (-15 + 6 * u))
                self.q = tuple(
                    a + (b - a) * blend for a, b in zip(start, target)
                )
                if u == 1:
                    self.route = None
            else:
                self.q = self.target
        dt = now - self.previous
        self.qd = (
            tuple((a - b) / dt for a, b in zip(self.q, previous))
            if dt > 0
            else (0.0,) * 6
        )
        self.previous = now
        self.sequence += 1
        return self.q

    def snapshot(self, _now):
        """Describe the last applied update, never a new sample from a send."""
        return {
            "source": self.source,
            "time_s": self.previous - self.began,
            "sequence": self.sequence,
            "acquired_ns": round(self.previous * 1e9),
            "q": self.q,
            "qd": self.qd,
            "gripper_position": self.gripper_position,
            "gripper_open": self.gripper_position == 0,
            "active": self.active,
            "fault": self.fault,
        }
