"""Terminal input and control-loop pacing without backend-specific commands."""

import contextlib
import os
import select
import termios
import time
import tty

from ur12e_collection import timing


@contextlib.contextmanager
def keyboard(stream):
    """Preserve signal handling and restore the terminal after any failure."""
    if not stream.isatty():
        raise ValueError("interactive session requires a terminal")
    descriptor = stream.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        yield lambda: _read(descriptor)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _read(descriptor):
    if not select.select([descriptor], [], [], 0)[0]:
        return []
    data = os.read(descriptor, 64)
    if not data:
        raise EOFError("session terminal closed")
    return [chr(value) for value in data if value in (32, 97)]


def drive(owner, read_keys) -> dict:
    """Space/a control only the current phase; Ctrl+C never requests HOME."""
    previous = None
    period = round(1e9 / owner.snapshot["control"]["control_hz"])
    deadline = time.monotonic_ns()
    try:
        while True:
            if owner.state != previous:
                print(f"session: {owner.state}", flush=True)
                previous = owner.state
            for key in read_keys():
                owner.key(key, time.monotonic_ns())
            owner.step()
            deadline = timing.next_deadline(
                deadline, time.monotonic_ns(), period
            )
            time.sleep(max(0, (deadline - time.monotonic_ns()) / 1e9))
    except (KeyboardInterrupt, EOFError):
        return {"state": "interrupted", "episodes": owner.completed}
