"""A bounded, non-destructive latest view shared by two local processes."""

import json

CAPACITY = 16384


class Latest:
    """Replace a complete view under a short lock; reads never consume it."""

    def __init__(self, context):
        self.buffer = context.RawArray("B", CAPACITY)
        self.size = context.RawValue("I", 0)
        self.version = context.RawValue("Q", 0)
        self.lock = context.Lock()

    def publish(self, value: dict) -> bool:
        """Keep the previous view if a reader temporarily holds the lock."""
        payload = json.dumps(value, allow_nan=False).encode("utf-8")
        if len(payload) > CAPACITY:
            raise ValueError("live leader view exceeds shared capacity")
        if not self.lock.acquire(timeout=0.001):
            return False
        try:
            memoryview(self.buffer).cast("B")[: len(payload)] = payload
            self.size.value = len(payload)
            self.version.value += 1
        finally:
            self.lock.release()
        return True

    def read(self, previous: int) -> tuple[int, dict] | None:
        """Never wait for a stalled/killed publisher or erase a valid view."""
        if not self.lock.acquire(block=False):
            return None
        try:
            version = self.version.value
            if version == previous:
                return None
            payload = bytes(
                memoryview(self.buffer).cast("B")[: self.size.value]
            )
        finally:
            self.lock.release()
        return version, json.loads(payload)
