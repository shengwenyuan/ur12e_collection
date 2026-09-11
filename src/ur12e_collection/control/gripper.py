"""Bounded Robotiq commands on an injected, exclusively owned connection."""

import time

from ur12e_collection import hande


class Client(hande.Reader):
    """Use an authorized connection; there is no host constructor."""

    # An injected socket deliberately bypasses Reader's network constructor.
    # pylint: disable-next=super-init-not-called
    def __init__(self, connection):
        self.connection = connection
        self.closed = False
        self.requested = None

    def _set(self, fields):
        if self.closed:
            raise RuntimeError("Hand-E command owner closed")
        for key, value in fields.items():
            valid_integer = isinstance(value, int) and not isinstance(
                value, bool
            )
            if (
                key not in ("POS", "SPE", "FOR", "GTO", "ACT")
                or not valid_integer
                or not 0 <= value <= 255
                or (key in ("GTO", "ACT") and value not in (0, 1))
            ):
                raise ValueError("invalid raw Hand-E command")
        try:
            deadline = time.monotonic_ns() + 250_000_000
            self.connection.settimeout(0.25)
            body = " ".join(f"{key} {value}" for key, value in fields.items())
            self.connection.sendall(f"SET {body}\n".encode("ascii"))
            # The URCap SET acknowledgement is exactly three bytes, no newline.
            reply = bytearray()
            while len(reply) < 3:
                remaining = (deadline - time.monotonic_ns()) / 1e9
                if remaining <= 0:
                    raise TimeoutError("Hand-E command acknowledgement timeout")
                self.connection.settimeout(remaining)
                part = self.connection.recv(3 - len(reply))
                if not part:
                    raise ConnectionError("Hand-E command connection closed")
                reply.extend(part)
            if bytes(reply) != b"ack" or time.monotonic_ns() > deadline:
                raise ValueError("Hand-E command not acknowledged")
        except Exception:
            self.close()
            raise

    def activate(self):
        """Request activation explicitly; startup and move never activate."""
        self._set({"ACT": 1})

    def move(self, position: int, speed: int, force: int):
        """Keep successful requests separate from measured POS/PRE feedback."""
        registers, _ = self.read()
        values = dict(registers)
        if values["STA"] != 3 or values["FLT"]:
            raise RuntimeError("Hand-E is not ready for a position command")
        self._set({"POS": position, "SPE": speed, "FOR": force, "GTO": 1})
        self.requested = position

    def hold(self):
        """Retain the last grasp request without release or reset."""
        if self.closed:
            raise RuntimeError("Hand-E command owner closed")
