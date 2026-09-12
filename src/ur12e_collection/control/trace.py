"""Bounded asynchronous commissioning evidence, separate from episodes."""

import dataclasses
import json
import queue
import threading
import time


class Trace:
    """Fail the owner on evidence overflow; never stall its motion loop."""

    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=False)
        self.path = directory / "trace.jsonl"
        self.pending = queue.Queue(maxsize=4096)
        self.error = None
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="control-trace"
        )
        self.thread.start()

    def emit(self, event, **values):
        """Retain event and host time; dataclasses preserve source clocks."""
        if self.error:
            raise RuntimeError(self.error)
        self.pending.put_nowait(
            {"event": event, "monotonic_ns": time.monotonic_ns(), **values}
        )

    def _run(self):
        try:
            with self.path.open("x", encoding="utf-8") as stream:
                while True:
                    row = self.pending.get()
                    if row is None:
                        break
                    stream.write(
                        json.dumps(
                            row, default=dataclasses.asdict, allow_nan=False
                        )
                        + "\n"
                    )
                    stream.flush()
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.error = str(error)

    def close(self):
        """Bounded flush; incomplete traces do not attest successful stops."""
        self.pending.put(None, timeout=2)
        self.thread.join(3)
        if self.thread.is_alive() or self.error:
            raise RuntimeError(self.error or "control trace did not finish")
