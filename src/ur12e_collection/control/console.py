"""Terminal input and control-loop pacing without backend-specific commands."""

import contextlib
import os
import select
import termios
import time
import tty


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
    try:
        while True:
            started = time.monotonic()
            if owner.state != previous:
                print(f"session: {owner.state}", flush=True)
                previous = owner.state
            for key in read_keys():
                owner.key(key, time.monotonic_ns())
            owner.step()
            time.sleep(max(0, 0.02 - (time.monotonic() - started)))
    except (KeyboardInterrupt, EOFError):
        return {"state": "interrupted", "episodes": owner.completed}
