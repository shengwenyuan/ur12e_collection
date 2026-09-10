"""Stationary capture checkpoints consume readback and never issue motion."""

from ur12e_collection.control.model import ControlError, Limits, State, distance


class Checkpoint:
    """One target, a settled start and an exact two-second receipt window."""

    def __init__(self, pose_id: str, target: tuple, limits: Limits):
        limits.check(target)
        if not isinstance(pose_id, str) or not pose_id:
            raise ValueError("checkpoint identity required")
        self.pose_id, self.target, self.limits = pose_id, target, limits
        self.state = "approaching"
        self.settled_ns = self.start_ns = self.last_progress_ns = None
        self.previous = None
        self.images = 0

    def _stationary(self, state):
        return (
            distance(state.q, self.target) < self.limits.arrival
            and max(map(abs, state.qd)) < self.limits.stopped_speed
        )

    def update(self, state: State, now_ns: int) -> None:
        """Require actual arrival and continuous fresh stationary feedback."""
        if self.state in ("failed", "complete"):
            raise ControlError("checkpoint is no longer active")
        try:
            self.limits.check(state.q)
            if (state.robot_mode, state.safety_mode) != (7, 1):
                raise ControlError("checkpoint robot mode is not normal")
            if not 0 <= now_ns - state.received_ns <= self.limits.freshness_ns:
                raise ControlError("checkpoint feedback is stale or future")
            if (
                self.previous is None
                or state.timestamp > self.previous.timestamp
            ):
                self.last_progress_ns = now_ns
            elif state.timestamp < self.previous.timestamp:
                raise ControlError("checkpoint controller clock moved backward")
            if now_ns - self.last_progress_ns > self.limits.freshness_ns:
                raise ControlError("checkpoint controller feedback stopped")
            self.previous = state
            if not self._stationary(state):
                if self.state == "capturing":
                    raise ControlError("robot moved during calibration dwell")
                self.settled_ns = None
                return
            self.settled_ns = (
                now_ns if self.settled_ns is None else self.settled_ns
            )
            if (
                self.state == "approaching"
                and now_ns - self.settled_ns >= 100_000_000
            ):
                self.state, self.start_ns = "capturing", now_ns
        except Exception:
            self.state = "failed"
            raise

    def image(self, receipt_ns: int, state: State) -> bool:
        """Accept an in-window image with an actual preceding pose readback."""
        if (
            self.state != "capturing"
            or not self.start_ns <= receipt_ns < self.start_ns + 2_000_000_000
        ):
            return False
        if (
            not 0 <= receipt_ns - state.received_ns <= 50_000_000
            or not self._stationary(state)
            or (state.robot_mode, state.safety_mode) != (7, 1)
        ):
            self.state = "failed"
            raise ControlError("image has no fresh stationary preceding pose")
        self.images += 1
        return True

    def finish(self, now_ns: int) -> dict:
        """A full dwell and fresh final readback are required for completion."""
        if (
            self.state != "capturing"
            or now_ns < self.start_ns + 2_000_000_000
            or not self.images
            or now_ns - self.previous.received_ns > self.limits.freshness_ns
        ):
            raise ControlError("checkpoint capture is incomplete")
        self.state = "complete"
        return {
            "pose_id": self.pose_id,
            "start_receipt_ns": self.start_ns,
            "stop_receipt_ns": self.start_ns + 2_000_000_000,
            "accepted_images": self.images,
        }
