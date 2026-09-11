"""Read-only twin observations and explicitly disabled future policy sources."""

import dataclasses
import json
import queue
from typing import Protocol


class ObservationProvider(Protocol):
    """Provide immutable observations; never grant control ownership."""

    def drain(self) -> tuple:
        """Return bounded recorded events with original provenance."""


class NullSink:
    """Default optional trajectory consumer with no resource ownership."""

    def records(self, _records):
        """Discard optional telemetry without touching the archive."""

    def status(self, _state, _episode=None):
        """Ignore optional session status."""

    def close(self):
        """No resources or device actions are required."""

    def health(self):
        """Report that the optional consumer is disabled."""
        return {"state": "disabled", "dropped_records": 0}


class MailboxSink(NullSink):
    """A stalled external consumer loses telemetry, never control-loop time."""

    def __init__(self, capacity=32):
        if (
            not isinstance(capacity, int) or isinstance(capacity, bool)
        ) or not 1 <= capacity <= 256:
            raise ValueError("bounded mailbox capacity required")
        self.queue = queue.Queue(capacity)
        self.dropped = 0
        self.closed = False

    def _put(self, item, count):
        if self.closed:
            self.dropped += count
            return
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            self.dropped += count

    def records(self, records):
        """Detach small typed records, preserving command/state separation."""
        if len(records) > 64:
            raise ValueError("bounded record batches required")
        values = tuple(
            json.loads(json.dumps(dataclasses.asdict(record), allow_nan=False))
            for record in records
        )
        self._put({"kind": "records", "records": values}, len(values))

    def status(self, state, episode=None):
        """Publish a phase event without queuing operator requests."""
        self._put({"kind": "phase", "state": state, "episode": episode}, 1)

    def drain(self):
        """Drain the bounded mailbox without callbacks into control."""
        values = []
        for _ in range(self.queue.maxsize):
            try:
                values.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return tuple(values)

    def health(self):
        """Telemetry loss does not imply authoritative archive loss."""
        return {
            "state": "closed" if self.closed else "online",
            "dropped_records": self.dropped,
            "queued_batches": self.queue.qsize(),
        }

    def close(self):
        """Close without waiting or issuing device commands."""
        self.closed = True


@dataclasses.dataclass(frozen=True)
class HandoverRequest:
    """A future request description is not an ownership grant."""

    source: str
    destination: str
    reason: str

    def __post_init__(self):
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.source, self.destination, self.reason)
        ):
            raise ValueError("handover identities and reason required")
        if self.source == self.destination:
            raise ValueError("handover requires different owners")


class DisabledPolicy:
    """Reserved interface; no policy target or takeover is enabled."""

    def read(self, _observation):
        """Never manufacture an action when policy integration is disabled."""
        raise RuntimeError("policy control is disabled")

    def request(self, _request: HandoverRequest):
        """A future handover request cannot acquire the active owner."""
        raise RuntimeError("policy handover is disabled")
