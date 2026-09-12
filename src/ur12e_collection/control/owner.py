"""One motion owner with bounded targets and measured arrival."""

import collections
import dataclasses

from ur12e_collection.control import settling
from ur12e_collection.control.model import (
    ControlError,
    Limits,
    Feedback,
    Target,
    Transport,
    distance,
)


@dataclasses.dataclass
class Progress:
    """Mutable trajectory state owned by a single control thread."""

    # These fields form one state, never independent motion owners.
    # pylint: disable=too-many-instance-attributes

    state: str = "hold"
    feedback: Feedback | None = None
    progress_ns: int = 0
    deadline_ns: int = 0
    settled_ns: int | None = None
    standstill: settling.Standstill | None = None
    target: Target | None = None
    velocity: tuple = (0.0,) * 6
    route: collections.deque = dataclasses.field(
        default_factory=collections.deque
    )
    route_speed: float = 0.0
    route_acceleration: float = 0.0
    moving_to: tuple | None = None
    error: str | None = None


class Controller:
    """Call from one thread; recorders consume events but never write motion."""

    def __init__(
        self, transport: Transport, limits: Limits, leader_source: str = "gello"
    ):
        self.transport = transport
        self.limits = limits
        if not isinstance(leader_source, str) or not leader_source:
            raise ControlError("authorized leader source is required")
        self.leader_source = leader_source
        self.progress = Progress()

    @property
    def state(self) -> str:
        """Expose the current ownership state."""
        return self.progress.state

    def _require(self, *states: str) -> None:
        if self.state not in states:
            raise ControlError(
                f"operation requires {states}, found {self.state}"
            )

    def fail(self, reason: str) -> None:
        """Latch the first fault and revoke queued targets before stopping."""
        p = self.progress
        if p.state in ("fault", "closed"):
            return
        was_servo = p.state == "following"
        p.error, p.state = reason, "fault"
        p.route.clear()
        p.target = None
        try:
            self.transport.stop(was_servo)
        except Exception as error:  # pylint: disable=broad-exception-caught
            p.error += f"; stop unconfirmed: {error}"

    def tick(self, now_ns: int) -> Feedback:
        """Validate feedback before refreshing the controller watchdog."""
        self._require("hold", "moving", "following", "stopping")
        p = self.progress
        try:
            feedback = self.transport.read()
            self.limits.check(feedback.q)
            if not feedback.motion_allowed:
                raise ControlError(feedback.motion_error)
            # The adapter stamps receipt after the read, not tick entry.
            age = now_ns - feedback.received_ns
            if age < -100_000_000 or age > self.limits.freshness_ns:
                raise ControlError("feedback receipt is stale or future")
            if p.feedback is None or feedback.timestamp > p.feedback.timestamp:
                p.progress_ns = now_ns
            elif feedback.timestamp < p.feedback.timestamp:
                raise ControlError("controller timestamp moved backward")
            if now_ns - p.progress_ns > self.limits.freshness_ns:
                raise ControlError("controller feedback stopped progressing")
            p.feedback = feedback
            if (
                p.state == "following"
                and now_ns - p.target.created_ns > self.limits.freshness_ns
            ):
                raise ControlError("leader input is stale")
            if p.state in ("moving", "stopping") and now_ns > p.deadline_ns:
                raise ControlError("motion or stop timed out")
            self.transport.heartbeat()
            self._settle(feedback, now_ns)
            return feedback
        except Exception as error:
            self.fail(str(error))
            raise ControlError(str(error)) from error

    def _settle(self, feedback: Feedback, now_ns: int) -> None:
        p = self.progress
        if p.state == "stopping":
            if p.standstill.update(feedback.qd, feedback.timestamp, now_ns):
                p.state, p.moving_to = "hold", None
            return
        stopped = max(abs(v) for v in feedback.qd) < self.limits.stopped_speed
        arrived = p.state == "stopping" or (
            p.moving_to is not None
            and distance(feedback.q, p.moving_to) < self.limits.arrival
        )
        if p.state in ("moving", "stopping") and arrived and stopped:
            if p.settled_ns is None:
                p.settled_ns = now_ns
            if now_ns - p.settled_ns >= 100_000_000:
                if p.state == "moving" and p.route:
                    self._next_move(now_ns)
                else:
                    p.state, p.moving_to = "hold", None
        else:
            p.settled_ns = None

    def _next_move(self, now_ns: int) -> None:
        p = self.progress
        p.moving_to = p.route.popleft()
        self.transport.move(p.moving_to, p.route_speed, p.route_acceleration)
        p.deadline_ns = now_ns + 60_000_000_000
        p.settled_ns = None

    def route(
        self, points: tuple, start: tuple, now_ns: int, *, ready: bool = False
    ) -> None:
        """Validate every waypoint and the measured start before motion."""
        self._require("hold")
        p = self.progress
        try:
            if not points or not isinstance(points, tuple):
                raise ControlError("route needs explicit immutable waypoints")
            self.limits.check(start)
            for point in points:
                self.limits.check(point)
            if (
                p.feedback is None
                or distance(p.feedback.q, start) > self.limits.arrival
            ):
                raise ControlError("route start differs from measured position")
            if now_ns - p.feedback.received_ns > self.limits.freshness_ns:
                raise ControlError("route start feedback is stale")
            if max(abs(v) for v in p.feedback.qd) >= self.limits.stopped_speed:
                raise ControlError("route start is moving")
            p.route = collections.deque(points)
            p.route_speed = (
                self.limits.ready_speed if ready else self.limits.speed
            )
            p.route_acceleration = (
                self.limits.ready_acceleration
                if ready
                else self.limits.acceleration
            )
            p.state = "moving"
            self._next_move(now_ns)
        except Exception as error:
            self.fail(str(error))
            raise ControlError(str(error)) from error

    def go_ready(self, now_ns: int) -> None:
        """Use the same motion path with dedicated bounded READY parameters."""
        if self.progress.feedback is None:
            raise ControlError("READY requires measured start")
        self.route(
            (self.limits.ready,), self.progress.feedback.q, now_ns, ready=True
        )

    def engage(self, target: Target, now_ns: int) -> None:
        """Acquire following after position and freshness alignment."""
        self._require("hold")
        p = self.progress
        try:
            if target.source_id != self.leader_source:
                raise ControlError("unauthorized leader source")
            self.limits.check(target.q)
            if (
                p.feedback is None
                or distance(p.feedback.q, target.q) > self.limits.arrival
            ):
                raise ControlError("leader engagement pose mismatch")
            if not 0 <= now_ns - target.created_ns <= self.limits.freshness_ns:
                raise ControlError("leader engagement is stale or future")
            age = now_ns - p.feedback.received_ns
            if age < -100_000_000 or age > self.limits.freshness_ns:
                raise ControlError("engagement feedback is stale or future")
            if max(abs(v) for v in p.feedback.qd) >= self.limits.stopped_speed:
                raise ControlError("engagement requires a stopped arm")
            p.target, p.velocity, p.state = target, (0.0,) * 6, "following"
        except Exception as error:
            self.fail(str(error))
            raise ControlError(str(error)) from error

    def follow(self, target: Target, now_ns: int) -> None:
        """Reject invalid intent without clamping or angle wrapping."""
        self._require("following")
        p = self.progress
        try:
            if target.source_id != self.leader_source:
                raise ControlError("unauthorized leader source")
            self.limits.check(target.q)
            if (
                target.sequence <= p.target.sequence
                or target.created_ns <= p.target.created_ns
            ):
                raise ControlError("leader sequence or time did not advance")
            if not 0 <= now_ns - target.created_ns <= self.limits.freshness_ns:
                raise ControlError("leader target is stale or future")
            dt = (target.created_ns - p.target.created_ns) / 1e9
            if dt > self.limits.freshness_ns / 1e9:
                raise ControlError("leader input gap")
            if distance(target.q, p.target.q) > self.limits.step:
                raise ControlError("leader target step exceeded")
            velocity = tuple((a - b) / dt for a, b in zip(target.q, p.target.q))
            if max(abs(v) for v in velocity) > self.limits.speed:
                raise ControlError("leader target velocity exceeded")
            if (
                max(abs(a - b) / dt for a, b in zip(velocity, p.velocity))
                > self.limits.acceleration
            ):
                raise ControlError("leader target acceleration exceeded")
            self.transport.servo(target.q)
            p.target, p.velocity = target, velocity
        except Exception as error:
            self.fail(str(error))
            raise ControlError(str(error)) from error

    def halt(self, now_ns: int) -> None:
        """Revoke following now; verify deceleration in subsequent ticks."""
        self._require("hold", "moving", "following")
        p = self.progress
        was_servo = p.state == "following"
        p.route.clear()
        p.target = None
        p.state, p.deadline_ns, p.settled_ns = (
            "stopping",
            now_ns + settling.STOP_TIMEOUT_NS,
            None,
        )
        p.standstill = settling.Standstill(self.limits.freshness_ns)
        try:
            self.transport.stop(was_servo)
        except Exception as error:
            self.fail(str(error))
            raise ControlError(str(error)) from error

    def close(self) -> None:
        """Release an already-stopped owner; active closure is a fault."""
        if self.state not in ("hold", "fault", "closed"):
            self.fail("owner closed during motion")
        self.transport.close()
        self.progress.state = "closed"
