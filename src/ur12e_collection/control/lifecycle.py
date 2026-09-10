"""Keyboard transitions independent of device and storage backends."""

from ur12e_collection.control.model import ControlError


class Lifecycle:
    """One explicit transition per distinct key press; no automatic restart."""

    def __init__(self):
        self.state = "needs_home"
        self.last_key_ns = None
        self.discard = False

    def key(self, key: str, now_ns: int) -> str | None:
        """Return an operation for the owner; busy states ignore queued keys."""
        if key not in (" ", "a") or self.state in ("fault", "closed"):
            return None
        previous, self.last_key_ns = self.last_key_ns, now_ns
        if previous is not None and now_ns - previous < 250_000_000:
            return None
        transition = {
            (" ", "needs_home"): ("homing", "home"),
            (" ", "held"): ("homing", "home"),
            (" ", "ready"): ("preparing", "prepare"),
            (" ", "recording"): ("stopping", "stop"),
            ("a", "recording"): ("stopping", "stop"),
            ("a", "held"): ("held", "discard"),
        }.get((key, self.state))
        if transition is None:
            return None
        self.state, operation = transition
        if key == "a":
            self.discard = True
        elif operation == "prepare":
            self.discard = False
        return operation

    def complete(self, operation: str) -> None:
        """Advance only after the operation has produced verified completion."""
        transition = {
            "home": ("homing", "ready"),
            "prepare": ("preparing", "recording"),
            "stop": ("stopping", "finalizing"),
            "finalize": ("finalizing", "held"),
        }.get(operation)
        if transition is None or self.state != transition[0]:
            raise ControlError(
                f"invalid completion {operation} in {self.state}"
            )
        self.state = transition[1]

    def fail(self) -> None:
        """Require a new session after a fault; keys cannot clear the latch."""
        self.state = "fault"

    def close(self) -> None:
        """Mark shutdown after the caller has revoked active ownership."""
        self.state = "closed"
