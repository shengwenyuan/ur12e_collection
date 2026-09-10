"""Read-only Robotiq URCap client; deliberately no activation or SET API."""

import socket
import time

from ur12e_collection import wire

REGISTERS = ("POS", "PRE", "STA", "OBJ", "FLT", "COU")


class Reader:
    """One socket owner; a malformed or timed-out poll requires a new reader."""

    def __init__(self, host: str, port: int):
        self.connection = socket.create_connection((host, port), timeout=1)
        self.closed = False

    def read(self) -> tuple:
        """Return raw named registers and the start of this non-atomic poll."""
        if self.closed:
            raise RuntimeError("Hand-E reader closed")
        try:
            return self._poll()
        except Exception:
            self.close()
            raise

    def _poll(self) -> tuple:
        started = time.monotonic_ns()
        values = []
        for register in REGISTERS:
            remaining = (started + 250_000_000 - time.monotonic_ns()) / 1e9
            if remaining <= 0:
                raise TimeoutError("Hand-E poll exceeded 250 ms")
            self.connection.settimeout(remaining)
            self.connection.sendall(f"GET {register}\n".encode("ascii"))
            line = wire.line(self.connection, started + 250_000_000, 64)
            parts = line.decode("ascii").split()
            if (
                not line.endswith(b"\n")
                or len(parts) != 2
                or parts[0] != register
                or not parts[1].isdecimal()
                or not 0 <= int(parts[1]) <= 255
            ):
                raise ValueError(f"invalid Hand-E reply for {register}")
            values.append((register, int(parts[1])))
        if time.monotonic_ns() - started > 250_000_000:
            raise TimeoutError("Hand-E poll exceeded 250 ms")
        return tuple(values), started

    def close(self) -> None:
        """Close local resources only; never change gripper state."""
        self.closed = True
        self.connection.close()
