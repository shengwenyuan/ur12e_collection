"""Bounded local-file transport and conservative monotonic clock alignment."""

import json
import pathlib
import time
import uuid

MAX_RTT_NS = 25_000_000
MESSAGE_BYTES = 16384


def write(path: pathlib.Path, value: dict) -> None:
    """Publish one complete local message; never expose a partial JSON file."""
    payload = json.dumps(value, allow_nan=False)
    if len(payload) > MESSAGE_BYTES:
        raise ValueError("leader bridge message too large")
    # Keep a constant inode length across Docker Desktop bind-mount renames.
    # Variable lengths can be observed with stale file-size metadata.
    payload = payload.ljust(MESSAGE_BYTES)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read(path: pathlib.Path) -> dict | None:
    """Bound message size and tolerate only an absent initial message."""
    try:
        with path.open("rb") as stream:
            payload = stream.read(MESSAGE_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(payload) > MESSAGE_BYTES:
        raise ValueError("leader bridge message too large")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("leader bridge requires an object")
    return value


def bracket(
    start_ns: int, host_ns: int, end_ns: int, max_rtt_ns=MAX_RTT_NS
) -> tuple[int, int]:
    """The host observation occurred between the two owner-clock readings."""
    if any(
        not isinstance(v, int) or isinstance(v, bool)
        for v in (start_ns, host_ns, end_ns)
    ):
        raise ValueError("clock handshake requires integer nanoseconds")
    if not 0 <= end_ns - start_ns <= max_rtt_ns:
        raise ValueError(
            f"leader clock round trip exceeds {max_rtt_ns / 1e6:g} ms"
        )
    return start_ns - host_ns, end_ns - host_ns


class Clock:
    """Keep one conservative offset; clock changes require restart."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.pending = None
        self.due_ns = 0
        self.bounds = None

    def request(self, now_ns):
        """Issue one nonce-bound request; it carries no device instruction."""
        self.pending = (uuid.uuid4().hex, now_ns)
        write(
            self.root / "clock-request.json",
            {
                "nonce": self.pending[0],
                "request_ns": now_ns,
            },
        )

    def receive(self, now_ns=None, *, max_rtt_ns=MAX_RTT_NS):
        """Reject replayed replies and retain the initial clock bracket."""
        nonce, started = self.pending
        reply = read(self.root / "clock-reply.json")
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        if reply and reply.get("nonce") == nonce:
            if reply.get("request_ns") != started:
                raise ValueError("leader clock reply differs from request")
            bounds = bracket(started, reply["host_ns"], now_ns, max_rtt_ns)
            self.pending = None
            return bounds
        if now_ns - started > max_rtt_ns:
            raise ValueError("leader clock reply expired")
        return None

    def synchronize(self):
        """Use the best of five bounded startup round trips."""
        candidates = []
        for _ in range(5):
            self.request(time.monotonic_ns())
            try:
                while True:
                    result = self.receive()
                    if result is not None:
                        candidates.append(result)
                        break
                    time.sleep(0.001)
            except ValueError:
                self.pending = None
        if not candidates:
            raise ValueError("cannot bound leader clock transport delay")
        self.bounds = min(candidates, key=lambda item: item[1] - item[0])
        self.due_ns = time.monotonic_ns() + 1_000_000_000

    def check(self, now_ns):
        """Recheck clocks without blocking the control loop."""
        if self.pending:
            current = self.receive(max_rtt_ns=100_000_000)
            if current is not None:
                if max(current[0], self.bounds[0]) > min(
                    current[1], self.bounds[1]
                ):
                    raise ValueError("leader clock alignment changed")
                self.due_ns = now_ns + 1_000_000_000
        elif now_ns >= self.due_ns:
            self.request(now_ns)
