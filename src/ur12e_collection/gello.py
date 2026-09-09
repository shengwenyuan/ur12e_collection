"""M04 unavailable leader: an explicit interface hook, never fake readiness."""

from typing import NoReturn


class GelloUnavailableError(RuntimeError):
    """Raised when physical leader behavior is requested before integration."""


class UnavailableGello:
    """Keep the future leader API available without inventing device state."""

    def health(self) -> dict:
        """Report the actual integration blocker."""
        return {
            "state": "unavailable",
            "ready": False,
            "reason": "hardware_pending",
        }

    def read_state(self) -> None:
        """Return no observation while hardware integration is unavailable."""
        return None

    def move_to(self, q_rad: tuple, limits: tuple) -> NoReturn:
        """Reject a motion request without touching any hardware."""
        del q_rad, limits  # Unused: no target can enable an unavailable device.
        raise GelloUnavailableError("GELLO hardware integration is unavailable")

    def hold(self) -> NoReturn:
        """Do not claim powered holding without an actual device."""
        raise GelloUnavailableError("GELLO holding is unverified")

    def stop(self) -> NoReturn:
        """Do not claim successful stopping without an actual device."""
        raise GelloUnavailableError("GELLO stopping is unverified")
