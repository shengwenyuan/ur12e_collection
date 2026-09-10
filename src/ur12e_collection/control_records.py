"""Independent authority and provenance validation for controlled episodes."""


class Validator:
    """Require bounded ownership and truthful intent, command and feedback."""

    def __init__(self, snapshot: dict):
        self.context = snapshot.get("control")
        self.previous = {}
        self.boundaries = {}
        self.receipts = []
        self.pending_intent = None
        self.pending_state = None

    def frames(self, group) -> None:
        """Retain only receipt extrema, not camera payloads."""
        if self.context:
            for frame in group.members:
                self._receipt(frame.color.time.received_monotonic_ns)

    def _receipt(self, receipt):
        self.receipts = (
            [min(self.receipts[0], receipt), max(self.receipts[1], receipt)]
            if self.receipts
            else [receipt, receipt]
        )

    def check(self, record, timestamp_ns: int) -> None:
        """Validate independent streams and the sent-command relationship."""
        if self.context is None:
            if record.kind == "authority_event":
                raise ValueError("authority requires a control snapshot")
            return
        sources = {
            "leader_intent": "leader_id",
            "sent_command": "command_id",
            "follower_state": "arm_id",
            "ur_feedback": "arm_id",
            "authority_event": "owner_id",
        }
        source = sources.get(record.kind)
        if source is None:
            raise ValueError("undeclared controlled-episode record")
        p = record.provenance
        if p.source_id != self.context[source]:
            raise ValueError("control source differs from snapshot")
        if timestamp_ns != (
            p.time.received_monotonic_ns + self.context["monotonic_to_unix_ns"]
        ):
            raise ValueError("control timestamp must preserve mapped receipt")
        expected_clock = (
            "ur_controller_uptime"
            if record.kind in ("follower_state", "ur_feedback")
            else "host_monotonic"
        )
        if p.time.source_clock != expected_clock or p.time.source_ns is None:
            raise ValueError("control source clock differs")
        if expected_clock == "host_monotonic" and (
            p.time.source_ns != p.time.received_monotonic_ns
        ):
            raise ValueError("host control timestamps must preserve event time")
        previous = self.previous.get(record.kind)
        if previous is not None and (
            p.sequence != previous.sequence + 1
            or p.time.received_monotonic_ns
            <= previous.time.received_monotonic_ns
            or p.time.source_ns <= previous.time.source_ns
        ):
            raise ValueError("control stream sequence or time did not advance")
        self.previous[record.kind] = p
        if record.kind == "authority_event":
            self._authority(record)
        else:
            self._sample(record)

    def _authority(self, record):
        expected = "acquired" if not self.boundaries else "released"
        if record.action != expected or record.action in self.boundaries:
            raise ValueError("authority must be acquired then released once")
        self.boundaries[record.action] = (
            record.provenance.time.received_monotonic_ns
        )

    def _sample(self, record):
        if getattr(record, "gripper_request_raw", None) is not None or (
            getattr(record, "gripper_position_raw", None) is not None
        ):
            raise ValueError("bypassed Hand-E must not produce values")
        if record.joint_positions_rad is None:
            raise ValueError("controlled episode needs actual arm values")
        self._receipt(record.provenance.time.received_monotonic_ns)
        if record.kind == "leader_intent":
            if self.pending_intent is not None:
                raise ValueError("previous intent has no successful command")
            self.pending_intent = record
        elif record.kind == "sent_command":
            intent = self.pending_intent
            if intent is None or (
                intent.joint_positions_rad != record.joint_positions_rad
                or intent.provenance.time.received_monotonic_ns
                > record.provenance.time.received_monotonic_ns
            ):
                raise ValueError("sent command differs from preceding intent")
            self.pending_intent = None
        elif record.kind == "follower_state":
            if self.pending_state is not None:
                raise ValueError("follower state has no UR readback")
            self.pending_state = record
        elif record.kind == "ur_feedback":
            state = self.pending_state
            if state is None or (
                state.provenance != record.provenance
                or state.joint_positions_rad != record.joint_positions_rad
            ):
                raise ValueError(
                    "follower state differs from paired UR readback"
                )
            self.pending_state = None

    def finish(self) -> None:
        """An incomplete control interval must never become a valid episode."""
        if self.context is None:
            return
        if (
            set(self.previous)
            != {
                "authority_event",
                "leader_intent",
                "sent_command",
                "follower_state",
                "ur_feedback",
            }
            or self.pending_intent is not None
        ):
            raise ValueError("controlled episode is missing required records")
        if set(self.boundaries) != {"acquired", "released"}:
            raise ValueError("control authority interval is incomplete")
        if not (
            self.boundaries["acquired"]
            <= self.receipts[0]
            <= self.receipts[1]
            < self.boundaries["released"]
        ):
            raise ValueError("observation lies outside control authority")
