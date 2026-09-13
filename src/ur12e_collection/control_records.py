"""Independent authority and provenance validation for controlled episodes."""


class Validator:
    """Require bounded ownership and truthful intent, command and feedback."""

    def __init__(self, snapshot: dict):
        self.context = snapshot.get("control")
        self.previous = {}
        self.counts = {}
        self.first = {}
        self.maximum_gap = (self.context or {}).get(
            "max_control_gap_ns", 250_000_000
        )
        self.boundaries = {}
        self.receipts = []
        self.pending_intent = None
        self.pending_state = None
        self.leader_audit = None

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
        if self.context.get("hande") == "urcap":
            sources["hande_feedback"] = "hande_id"
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
        self._clock(record)
        previous = self.previous.get(record.kind)
        if previous is not None and (
            p.sequence != previous.sequence + 1
            or p.time.received_monotonic_ns
            <= previous.time.received_monotonic_ns
            or (
                p.time.source_ns is not None
                and p.time.source_ns <= previous.time.source_ns
            )
        ):
            raise ValueError("control stream sequence or time did not advance")
        if (
            previous is not None
            and record.kind != "authority_event"
            and p.time.received_monotonic_ns
            - previous.time.received_monotonic_ns
            > self.maximum_gap
        ):
            raise ValueError("control stream has an excessive receipt gap")
        self.first.setdefault(record.kind, p.time.received_monotonic_ns)
        self.previous[record.kind] = p
        self.counts[record.kind] = self.counts.get(record.kind, 0) + 1
        if record.kind == "authority_event":
            self._authority(record)
        else:
            self._sample(record)

    @staticmethod
    def _clock(record):
        p = record.provenance
        expected_clock = (
            "ur_controller_uptime"
            if record.kind in ("follower_state", "ur_feedback")
            else "host_monotonic"
        )
        if record.kind == "hande_feedback":
            expected_clock = "unavailable"
        if p.time.source_clock != expected_clock or (
            (p.time.source_ns is None) != (expected_clock == "unavailable")
        ):
            raise ValueError("control source clock differs")
        if expected_clock == "host_monotonic" and (
            p.time.source_ns != p.time.received_monotonic_ns
        ):
            raise ValueError("host control timestamps must preserve event time")

    def _authority(self, record):
        expected = "acquired" if not self.boundaries else "released"
        if record.action != expected or record.action in self.boundaries:
            raise ValueError("authority must be acquired then released once")
        if record.action == "acquired" and record.context is not None:
            if not self.context.get("leader_mapping"):
                raise ValueError("leader mapping not declared in snapshot")
            # pylint: disable-next=import-outside-toplevel
            from ur12e_collection.leader.audit import Audit

            self.leader_audit = Audit(
                record.context, record.provenance.time.received_monotonic_ns
            )
        if (
            record.action == "acquired"
            and self.context.get("leader_mapping")
            and self.leader_audit is None
        ):
            raise ValueError("relative leader baseline is missing")
        if (
            record.action == "acquired"
            and self.context.get("leader_mapping")
            and self.context["hande"] == "urcap"
            and self.leader_audit.gripper is None
        ):
            raise ValueError("relative gripper baseline is missing")
        self.boundaries[record.action] = (
            record.provenance.time.received_monotonic_ns
        )

    def _sample(self, record):
        if record.kind == "hande_feedback":
            self._receipt(record.provenance.time.received_monotonic_ns)
            return
        if self.context["hande"] == "bypassed" and (
            getattr(record, "gripper_request_raw", None) is not None
            or (getattr(record, "gripper_position_raw", None) is not None)
        ):
            raise ValueError("bypassed Hand-E must not produce values")
        if record.joint_positions_rad is None:
            raise ValueError("controlled episode needs actual arm values")
        self._receipt(record.provenance.time.received_monotonic_ns)
        if record.kind == "leader_intent":
            if self.pending_intent is not None:
                raise ValueError("previous intent has no successful command")
            self._leader_intent(record)
            self.pending_intent = record
        elif record.kind == "sent_command":
            intent = self.pending_intent
            if intent is None or (
                (
                    self.leader_audit is None
                    and intent.joint_positions_rad != record.joint_positions_rad
                )
                or intent.provenance.time.received_monotonic_ns
                > record.provenance.time.received_monotonic_ns
            ):
                raise ValueError("sent command differs from preceding intent")
            if self.leader_audit is not None:
                self.leader_audit.sent(record)
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
            != (
                {
                    "authority_event",
                    "leader_intent",
                    "sent_command",
                    "follower_state",
                    "ur_feedback",
                }
                | (
                    {"hande_feedback"}
                    if self.context["hande"] == "urcap"
                    else set()
                )
            )
            or self.pending_intent is not None
            or self.pending_state is not None
        ):
            raise ValueError("controlled episode is missing required records")
        if set(self.boundaries) != {"acquired", "released"}:
            raise ValueError("control authority interval is incomplete")
        duration = self.boundaries["released"] - self.boundaries["acquired"]
        minimum = self.context.get("minimum_command_hz", 0)
        if self.counts["sent_command"] * 1e9 <= minimum * duration:
            raise ValueError("recorded command rate is not above minimum")
        for kind, last in self.previous.items():
            if kind == "authority_event":
                continue
            if (
                self.first[kind] - self.boundaries["acquired"]
                > self.maximum_gap
                or self.boundaries["released"] - last.time.received_monotonic_ns
                > self.maximum_gap
            ):
                raise ValueError(
                    "control stream does not cover its authority interval"
                )
        if not (
            self.boundaries["acquired"]
            <= self.receipts[0]
            <= self.receipts[1]
            < self.boundaries["released"]
        ):
            raise ValueError("observation lies outside control authority")

    def _leader_intent(self, record):
        if self.leader_audit is not None:
            self.leader_audit.intent(record)
        elif record.acquisition is not None:
            raise ValueError("raw leader input has no calibration context")
