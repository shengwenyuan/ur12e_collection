"""Coordinate leader HOME, manual leading and current-position HOLD."""


class Coordinator:
    """The session owns this lifecycle; the transport owns device I/O."""

    def __init__(self, motion, binding_provider, *, supported: bool):
        if not isinstance(supported, bool):
            raise ValueError("operator/mechanical support must be explicit")
        self.motion = motion
        self.bindings = binding_provider
        self.supported = supported
        self.phase = "idle"

    def start_home(self, now_ns):
        """Require support before permitting a later torque-off handover."""
        if not self.supported:
            raise RuntimeError("leader support is unverified")
        if self.motion.blocked:
            raise RuntimeError("coordinated HOME blocked by cable clearance")
        self.motion.hold(now_ns, self.bindings())
        self.phase = "prepare_home"

    def home_ready(self, now_ns):
        """Both leader hold and powered HOME require measured settling."""
        result = self.motion.step(now_ns)
        if result == "held" and self.phase == "prepare_home":
            # Reuse the observation without fabricating another acquisition.
            self.motion.go_home(now_ns, observed=self.motion.previous)
            self.phase = "homing"
            return False
        return self.phase == "homing" and result == "held"

    def begin(self):
        """Transfer the supported leader before sampling a baseline."""
        if self.phase != "homing" or self.motion.state != "held":
            raise RuntimeError("leader is not at READY")
        self.motion.release(supported=self.supported)
        self.phase = "leading"

    def hold(self, now_ns):
        """Revoke input before requesting a measured current-position hold."""
        if self.phase not in ("leading", "prepare_home", "homing"):
            raise RuntimeError("leader has no active motion to hold")
        self.motion.hold(now_ns, self.bindings())
        self.phase = "holding"

    def held(self, now_ns):
        """Confirm leader hold before finalizing the shared handover."""
        return self.motion.step(now_ns) == "held"

    def close(self):
        """Close local resources; powered posture is retained."""
        self.motion.close()
