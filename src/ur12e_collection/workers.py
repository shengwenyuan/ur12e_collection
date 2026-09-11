"""Bounded cleanup for disposable native-SDK diagnostic processes."""

import multiprocessing
import signal
import time
from multiprocessing.process import BaseProcess


class Cancellation:
    """One-way shared byte; a killed waiter cannot block stop notification.

    Every writer stores only 1 and readers observe 0 or 1. This flag carries no
    other data or ordering guarantee. Waits use local polling, never a shared
    condition whose wake-up acknowledgement could be lost with a killed child.
    """

    def __init__(self, context: multiprocessing.context.BaseContext):
        self._flag = context.RawValue("B", 0)

    def set(self) -> None:
        """Request cancellation without waiting for any worker."""
        self._flag.value = 1

    def is_set(self) -> bool:
        """Observe the monotonic cancellation request."""
        return bool(self._flag.value)

    def wait(self, timeout: float | None = None) -> bool:
        """Wait locally for cancellation or the caller's elapsed-time bound."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            remaining = (
                0.005 if deadline is None else deadline - time.monotonic()
            )
            if remaining <= 0:
                return self.is_set()
            time.sleep(min(0.005, remaining))
        return True


def stop(process: BaseProcess, *, grace_s: float = 1) -> None:
    """Allow a reported worker to exit, then reap it with bounded escalation."""
    process.join(timeout=grace_s)
    for terminate in (process.terminate, process.kill):
        if not process.is_alive():
            return
        terminate()
        process.join(timeout=2)


def ignore_terminal_interrupt() -> None:
    """Let the parent own Ctrl+C and stop children through explicit channels."""
    if multiprocessing.parent_process() is not None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
