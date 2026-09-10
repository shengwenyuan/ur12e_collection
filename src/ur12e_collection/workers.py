"""Bounded cleanup for disposable native-SDK diagnostic processes."""

import multiprocessing
import signal
from multiprocessing.process import BaseProcess


def stop(process: BaseProcess) -> None:
    """Allow a reported worker to exit, then reap it with bounded escalation."""
    process.join(timeout=1)
    for terminate in (process.terminate, process.kill):
        if not process.is_alive():
            return
        terminate()
        process.join(timeout=2)


def ignore_terminal_interrupt() -> None:
    """Let the parent own Ctrl+C and stop children through explicit channels."""
    if multiprocessing.parent_process() is not None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
