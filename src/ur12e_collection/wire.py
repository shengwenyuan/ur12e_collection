"""Bounded ASCII line replies under one absolute monotonic deadline."""

import socket
import time


def line(connection: socket.socket, deadline_ns: int, limit: int) -> bytes:
    """A peer cannot extend the deadline by drip-feeding single bytes."""
    result = bytearray()
    while len(result) < limit:
        remaining = (deadline_ns - time.monotonic_ns()) / 1e9
        if remaining <= 0:
            raise TimeoutError("reply deadline exceeded")
        connection.settimeout(remaining)
        part = connection.recv(1)
        if not part:
            raise ConnectionError("peer closed before a complete reply")
        result.extend(part)
        if part == b"\n":
            if time.monotonic_ns() > deadline_ns:
                raise TimeoutError("reply deadline exceeded")
            return bytes(result)
    raise ValueError("reply exceeds length limit")
