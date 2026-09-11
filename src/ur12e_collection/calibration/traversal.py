"""Taught calibration routes under the existing exclusive controller."""

import collections
import dataclasses

from ur12e_collection import contracts
from ur12e_collection.calibration.checkpoint import Checkpoint
from ur12e_collection.control import model


@dataclasses.dataclass(frozen=True)
class Pose:
    """An explicit taught route, expected views and independent solver split."""

    pose_id: str
    waypoints: tuple
    roles: tuple
    split: str

    def __post_init__(self):
        if (
            not self.pose_id
            or not isinstance(self.waypoints, tuple)
            or not self.waypoints
        ):
            raise ValueError(
                "pose identity and explicit immutable route required"
            )
        if (
            not isinstance(self.roles, tuple)
            or not self.roles
            or len(set(self.roles)) != len(self.roles)
            or not set(self.roles) <= set(contracts.CAMERA_ROLES)
            or self.split not in ("training", "validation")
        ):
            raise ValueError("expected views and solver split required")
        for target in self.waypoints:
            model.joints(target)


class Traversal:
    """Motion finishes before two-second capture; vision never owns a robot."""

    def __init__(self, controller, poses, capture):
        if not isinstance(poses, tuple) or not 1 <= len(poses) <= 40:
            raise ValueError("a round requires 1..40 taught poses")
        if len({pose.pose_id for pose in poses}) != len(poses):
            raise ValueError("pose identities must be unique")
        for pose in poses:
            for target in pose.waypoints:
                controller.limits.check(target)
        self.controller, self.poses, self.capture = controller, poses, capture
        self.index = 0
        self.state = "idle"
        self.checkpoint = None
        self.feedback = collections.deque(maxlen=32)
        self.views = set()
        self.results = []

    def start(self, now_ns):
        """Use the measured start and the controller's validated route API."""
        if self.state != "idle":
            raise RuntimeError("calibration traversal already started")
        self._route(now_ns)

    def _route(self, now_ns):
        state = self.controller.progress.feedback
        if state is None:
            raise model.ControlError("calibration requires measured start")
        self.controller.route(
            self.poses[self.index].waypoints, state.q, now_ns, ready=True
        )
        self.state = "moving"
        self.checkpoint = None
        self.views.clear()
        self.feedback.clear()

    def step(self, now_ns):
        """Only actual stopped readback can start or complete a dwell."""
        if self.state in ("idle", "complete", "failed"):
            raise RuntimeError("calibration traversal is not active")
        try:
            state = self.controller.tick(now_ns)
            self.feedback.append(state)
            if self.controller.state != "hold":
                return
            pose = self.poses[self.index]
            if self.checkpoint is None:
                self.checkpoint = Checkpoint(
                    pose.pose_id, pose.waypoints[-1], self.controller.limits
                )
            self.checkpoint.update(state, max(now_ns, state.received_ns))
            self.state = self.checkpoint.state
            if (
                self.checkpoint.start_ns is not None
                and now_ns >= self.checkpoint.start_ns + 2_000_000_000
            ):
                if self.views != set(pose.roles):
                    raise ValueError(
                        "calibration checkpoint is missing valid camera views"
                    )
                report = self.checkpoint.finish(now_ns)
                self.results.append(
                    report | {"roles": pose.roles, "split": pose.split}
                )
                self.index += 1
                if self.index == len(self.poses):
                    self.state = "complete"
                else:
                    self._route(now_ns)
        except Exception:
            self.fail()
            raise

    def image(self, frame):
        """Associate preceding readback; rejected detection adds no evidence."""
        if self.state != "capturing":
            return False
        pose = self.poses[self.index]
        if frame.role not in pose.roles:
            return False
        receipt = frame.color.time.received_monotonic_ns
        previous = next(
            (s for s in reversed(self.feedback) if s.received_ns <= receipt),
            None,
        )
        if previous is None:
            return False
        try:
            if not self.checkpoint.image(receipt, previous):
                return False
            if self.capture(pose, frame, previous):
                self.views.add(frame.role)
                return True
            return False
        except Exception:
            self.fail()
            raise

    def fail(self):
        """Latch capture failure and stop the existing controller owner."""
        self.state = "failed"
        self.controller.fail("calibration traversal failed")
