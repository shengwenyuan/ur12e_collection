"""Persistent independent MCAP verifier, isolated from camera acquisition."""

import multiprocessing
import time

from ur12e_collection import archive, workers


def _worker(connection):
    workers.ignore_terminal_interrupt()
    try:
        connection.send(("ready", None))
        while True:
            arguments = connection.recv()
            if arguments is None:
                return
            try:
                result = archive.verify_mcap(*arguments)
                connection.send(("complete", result))
            # Invalid files and codec errors must return to the commit owner.
            # pylint: disable-next=broad-exception-caught
            except Exception as error:
                connection.send(("error", str(error)))
    except (EOFError, BrokenPipeError):
        return
    finally:
        connection.close()


class Verifier:
    """One bounded request at a time; cancellation never authorizes commit."""

    def __init__(self, abort):
        self.abort = abort
        ctx = multiprocessing.get_context("spawn")
        self.connection, child = ctx.Pipe()
        self.process = ctx.Process(
            target=_worker, args=(child,), name="mcap-verifier"
        )
        self.process.start()
        child.close()
        try:
            if self._receive(30)[0] != "ready":
                raise RuntimeError("verifier did not initialize")
        except BaseException:
            self.close()
            raise

    def _receive(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.abort.is_set():
                raise RuntimeError("verification owner aborted")
            if self.connection.poll(0.05):
                return self.connection.recv()
            if not self.process.is_alive():
                raise RuntimeError("verification process exited")
        raise TimeoutError("independent verification timed out")

    def verify(self, *arguments) -> dict:
        """Called by the writer thread after the MCAP file is fully closed."""
        self.connection.send(arguments)
        kind, result = self._receive(25)
        if kind != "complete":
            raise RuntimeError(f"independent verification failed: {result}")
        return result

    def close(self) -> None:
        """Reap the independent checker after recording ownership is revoked."""
        if self.process.is_alive():
            try:
                self.connection.send(None)
            except (BrokenPipeError, OSError):
                pass
        workers.stop(self.process)
        self.connection.close()
