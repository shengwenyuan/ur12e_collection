"""Mac-side read-only leader publisher for one isolated simulator rehearsal."""

import collections
import dataclasses
import json
import threading
import time

from ur12e_collection.leader import source
from ur12e_collection.simulation import bridge


class Publisher:
    """Own only a serial reader; no torque, HOME, HOLD or goal API exists."""

    def __init__(self, root, device, baudrate):
        self.root = root
        self.reader = source.Reader(device, baudrate)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.fault = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=False)
        try:
            self.reader.start()
            bridge.write(self.root / "inventory.json", self.reader.inventory)
            self.thread.start()
            return self
        except BaseException:
            self.reader.close()
            raise

    def _run(self):
        recent = collections.deque(maxlen=16)
        nonce = None
        try:
            with (self.root / "samples.jsonl").open("x") as trace:
                while not self.stop.is_set():
                    view = self.reader.mailbox.view()
                    if any(view.health.integers(64, 1)):
                        raise ValueError(
                            "live rehearsal requires torque-off leader"
                        )
                    fresh = self.reader.mailbox.drain()
                    for motion in fresh:
                        row = dataclasses.asdict(motion.sample)
                        recent.append(row)
                        trace.write(json.dumps(row) + "\n")
                    if fresh:
                        bridge.write(
                            self.root / "latest.json",
                            {
                                "epoch": self.reader.epoch,
                                "samples": list(recent),
                                "published_ns": time.monotonic_ns(),
                                "health_start_ns": view.health.start_ns,
                                "health_end_ns": view.health.end_ns,
                                "torque": view.health.integers(64, 1),
                                "hardware_error": view.health.integers(70, 1),
                                "health_errors": view.health.errors,
                            },
                        )
                    request = bridge.read(self.root / "clock-request.json")
                    if request and request["nonce"] != nonce:
                        bridge.write(
                            self.root / "clock-reply.json",
                            {
                                **request,
                                "host_ns": time.monotonic_ns(),
                            },
                        )
                        nonce = request["nonce"]
                    self.stop.wait(0.002)
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.fault = str(error)
            bridge.write(self.root / "latest.json", {"fault": self.fault})

    def __exit__(self, *_args):
        self.stop.set()
        self.thread.join(3)
        self.reader.close()
        if self.thread.is_alive():
            raise RuntimeError("leader publisher did not stop")
        bridge.write(
            self.root / "publisher-report.json",
            {
                "fault": self.fault,
                "epoch": self.reader.epoch,
                "traffic": self.reader.traffic,
                "motor_writes": False,
            },
        )
        bridge.write(self.root / "latest.json", {"fault": "publisher closed"})
