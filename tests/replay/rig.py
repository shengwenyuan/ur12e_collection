"""Persistent real-image replay for the shared recorder's source boundary."""

import dataclasses
import functools
import queue
import threading
import time
import uuid

from .feed import Cache
from ur12e_collection import contracts


class Rig:
    """Three bounded producers; no camera or hardware SDK is loaded."""

    def __init__(self, path, _config, _context, abort):
        self.cache = Cache(path)
        self.clock_id = f"replay:{uuid.uuid4().hex}"
        self.observations = self.cache.snapshot("probe", "fixture")["cameras"]
        self.abort = abort
        self.stop = threading.Event()
        self.queues = {role: queue.Queue(8) for role in contracts.CAMERA_ROLES}
        self.stats = {
            role: dict(frames=0, queue_peak=0, error=None, max_delivery_ms=0.0)
            for role in contracts.CAMERA_ROLES
        }
        self.threads = []
        self.offset = time.time_ns() - time.monotonic_ns()
        self.started = 0

    def start(self):
        self.started = time.monotonic_ns() + 200_000_000
        for role in contracts.CAMERA_ROLES:
            thread = threading.Thread(
                target=self._produce, args=(role,), name=f"replay-{role}"
            )
            self.threads.append(thread)
            thread.start()

    def _produce(self, role):
        sequence = 0
        try:
            while not self.stop.is_set() and not self.abort.is_set():
                due = self.started + self.cache.due(role, sequence)
                frame = self.cache.frame(
                    role,
                    sequence,
                    self.clock_id,
                    due,
                    self.started + self.offset,
                )
                if self.stop.wait(max(0, (due - time.monotonic_ns()) / 1e9)):
                    return
                now = time.monotonic_ns()
                frame = dataclasses.replace(
                    frame,
                    **{
                        kind: dataclasses.replace(
                            getattr(frame, kind),
                            time=dataclasses.replace(
                                getattr(frame, kind).time,
                                received_monotonic_ns=now,
                            ),
                        )
                        for kind in ("color", "depth")
                    },
                )
                self.queues[role].put_nowait(frame)
                self.stats[role]["frames"] += 1
                self.stats[role]["queue_peak"] = max(
                    self.stats[role]["queue_peak"], self.queues[role].qsize()
                )
                self.stats[role]["max_delivery_ms"] = max(
                    self.stats[role]["max_delivery_ms"], (now - due) / 1e6
                )
                sequence += 1
        except Exception as error:
            self.stats[role]["error"] = f"{type(error).__name__}: {error}"
            self.stop.set()

    def read(self):
        if (
            abs(time.time_ns() - time.monotonic_ns() - self.offset)
            > 100_000_000
        ):
            raise RuntimeError("replay host clock stepped")
        result = []
        for role, channel in self.queues.items():
            if self.stats[role]["error"]:
                raise RuntimeError(f"{role}: {self.stats[role]['error']}")
            for _ in range(8):
                try:
                    result.append(channel.get_nowait())
                except queue.Empty:
                    break
        return result

    def statistics(self):
        return self.stats

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(5)
            if thread.is_alive():
                raise TimeoutError("replay producer did not exit")
        self.cache.close()


def configuration(path):
    cache = Cache(path)
    try:
        config = cache.snapshot("probe", "fixture")["station"]
        return (
            config,
            functools.partial(Rig, path),
            {
                "cameras": {
                    "kind": "recorded_rgbd_replay",
                    "cache_sha256": cache.identity,
                    "frames_per_role": len(cache.groups),
                    "original_source": cache.manifest["source_metadata"],
                    "replays_usb_or_alignment_cost": False,
                },
                "arm": {"kind": "live_ursim"},
                "leader": {"kind": "recorded_encoder_replay"},
                "hande": {"kind": "bypassed"},
                "clock_domain": "one_linux_host_monotonic",
                "visual_action_correspondence": False,
            },
        )
    finally:
        cache.close()
