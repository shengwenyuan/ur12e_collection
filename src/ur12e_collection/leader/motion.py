"""Leader motion sequencing over an injected, exclusively owned transport."""

import dataclasses

from ur12e_collection.leader import coordinates, mapping


@dataclasses.dataclass(frozen=True)
class State:
    """Transport readback; epoch must change on torque, mode or power reset."""

    epoch: str
    counts: tuple
    torque: tuple
    received_ns: int
    moving: tuple = (False,) * 7
    errors: tuple = (0,) * 7

    def __post_init__(self):
        if not self.epoch or any(
            not isinstance(value, tuple) or len(value) != 7
            for value in (self.counts, self.torque, self.moving, self.errors)
        ):
            raise ValueError("complete immutable seven-axis state required")
        for value in self.counts:
            mapping.integer(value)
        if any(
            not isinstance(value, bool) for value in self.torque + self.moving
        ):
            raise ValueError("torque and motion flags must be boolean")
        mapping.integer(self.received_ns)


class Motion:
    """No serial constructor, automatic recovery or torque release on close."""

    def __init__(self, transport, home, bounds, *, blocked=(3,)):
        if len(home) != 7 or len(bounds) != 7:
            raise ValueError("seven HOME targets and intervals required")
        self.transport, self.home, self.bounds = transport, tuple(home), bounds
        self.blocked = frozenset(blocked)
        self.state = "idle"
        self.target = None
        self.deadline_ns = 0
        self.settled_ns = None
        self.previous = None
        self.epoch = None

    def _read(self, now_ns):
        if self.state in ("fault", "closed"):
            raise RuntimeError("leader motion owner unavailable")
        value = self.transport.read(now_ns)
        reset = self.epoch is not None and value.epoch != self.epoch
        reordered = False
        if self.previous is not None:
            delta = value.received_ns - self.previous.received_ns
            reordered = delta < 0 or (delta == 0 and value != self.previous)
        if (
            not 0 <= now_ns - value.received_ns <= 100_000_000
            or any(value.errors)
            or reordered
            or reset
        ):
            self.state = "fault"
            raise RuntimeError("leader motion feedback stale, reset or faulty")
        self.previous = value
        return value

    def _goals(self, goals):
        for motor_id, goal in goals.items():
            if motor_id in self.blocked:
                raise ValueError(f"active motion prohibited for ID{motor_id}")
            mapping.integer(goal)
            lower, upper = self.bounds[motor_id - 1]
            if not 0 <= lower <= goal <= upper <= 4095:
                raise ValueError("leader goal outside powered interval")

    def hold(self, now_ns, bindings=None):
        """Preload measured goals before torque; reject unknown coordinates."""
        try:
            value = self._read(now_ns)
            ids = [i for i in range(1, 8) if i not in self.blocked]
            goals = {}
            for i in ids:
                if value.torque[i - 1]:
                    goals[i] = value.counts[i - 1]
                else:
                    if bindings is None:
                        raise ValueError(
                            "verified torque-off bindings required"
                        )
                    binding = bindings[i - 1]
                    if not isinstance(binding, coordinates.PoweredAxis):
                        raise ValueError("powered coordinate binding required")
                    if binding.logical_count != value.counts[i - 1]:
                        raise ValueError("binding differs from measured hold")
                    goals[i] = binding.goal(value.counts[i - 1], value.epoch)
            self._goals(goals)
            self.transport.goals(goals)
            disabled = tuple(i for i in ids if not value.torque[i - 1])
            if disabled:
                self.transport.enable(disabled)
            self.epoch = None  # The next read must establish the new epoch.
            self.target = goals
            self.deadline_ns = now_ns + 2_000_000_000
            self.settled_ns = None
            self.state = "holding"
        except Exception:
            self.state = "fault"
            raise

    def go_home(self, now_ns, *, observed=None):
        """Preflight every axis before any HOME write."""
        try:
            if self.state != "held":
                raise RuntimeError(
                    "leader HOME requires confirmed powered hold"
                )
            value = self._read(now_ns) if observed is None else observed
            if (
                value is not self.previous
                or not 0 <= now_ns - value.received_ns <= 100_000_000
            ):
                raise ValueError("HOME observation is not current")
            goals = dict(enumerate(self.home, 1))
            self._goals(goals)
            if not all(value.torque):
                raise ValueError("leader HOME requires all seven torques")
            self.transport.goals(goals)
            self.target = goals
            self.state = "homing"
            self.deadline_ns = now_ns + 30_000_000_000
            self.settled_ns = None
        except Exception:
            self.state = "fault"
            raise

    def step(self, now_ns):
        """Confirm <=2-count error (0.176 degrees) for 200 ms."""
        value = self._read(now_ns)
        self.epoch = value.epoch
        if self.state not in ("holding", "homing", "held"):
            return self.state
        arrived = all(
            value.torque[i - 1]
            and not value.moving[i - 1]
            and abs(value.counts[i - 1] - goal) <= 2
            for i, goal in self.target.items()
        )
        if self.state == "held" and not arrived:
            self.state = "fault"
            raise RuntimeError("leader hold drift or torque loss")
        if arrived:
            if self.settled_ns is None:
                self.settled_ns = value.received_ns
            if value.received_ns - self.settled_ns >= 200_000_000:
                self.state = "held"
        else:
            self.settled_ns = None
        if self.state != "held" and now_ns > self.deadline_ns:
            self.state = "fault"
            raise TimeoutError("leader arrival unconfirmed")
        return self.state

    def release(self, *, supported):
        """Release for supported leading, never during close or failure."""
        if self.state != "held" or not supported or self.blocked:
            raise RuntimeError(
                "leader release requires supported complete hold"
            )
        self.transport.disable(tuple(range(1, 8)))
        self.epoch = None
        self.state = "leading"

    def close(self):
        """Keep powered posture; never issue an automatic torque-off command."""
        self.state = "closed"
        self.transport.close()
