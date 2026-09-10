"""Independent validation of read-only feedback provenance in MCAP files."""

from ur12e_collection import contracts

KINDS = {"ur_feedback": "ur", "hande_feedback": "hande"}


class Validator:
    """Require declared identities, monotonic samples and both sources."""

    def __init__(self, snapshot: dict):
        self.context = snapshot.get("feedback")
        self.previous = {}

    def check(self, record, timestamp_ns: int) -> None:
        """Verify receipt-mapped Unix and retain separate controller uptime."""
        device = KINDS.get(record.kind)
        if self.context is None:
            if device or record.kind == "authority_event":
                raise ValueError("feedback source missing from snapshot")
            return
        if device is None:
            raise ValueError(
                "read-only observation cannot contain action records"
            )
        provenance = record.provenance
        if provenance.source_id != self.context["devices"][device]["source_id"]:
            raise ValueError("feedback source differs from snapshot")
        expected = (
            provenance.time.received_monotonic_ns
            + self.context["monotonic_to_unix_ns"]
        )
        if timestamp_ns != expected:
            raise ValueError(
                "feedback publish time must preserve mapped receipt"
            )
        previous = self.previous.get(device)
        if previous is not None:
            if (
                provenance.sequence != previous.sequence + 1
                or provenance.time.received_monotonic_ns
                <= previous.time.received_monotonic_ns
                or provenance.time.received_monotonic_ns
                - previous.time.received_monotonic_ns
                > self.context["stale_ns"]
            ):
                raise ValueError("feedback sequence or freshness differs")
            if isinstance(record, contracts.URFeedback) and (
                provenance.time.source_ns <= previous.time.source_ns
            ):
                raise ValueError("controller time did not progress")
        self.previous[device] = provenance

    def frames(self, group) -> None:
        """Read-only timing is verified separately from control authority."""

    def finish(self) -> None:
        """An enabled source must contribute actual in-boundary feedback."""
        if self.context and set(self.previous) != set(KINDS.values()):
            raise ValueError("episode is missing required feedback")
