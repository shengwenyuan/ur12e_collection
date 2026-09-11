"""Persistent real-image replay for the shared recorder's source boundary."""

import dataclasses
import functools
import queue
import threading
import time
import uuid

from .feed import Cache
from ur12e_collection import contracts

PHASE_NS = {"wrist": 0, "third_left": 4_000_000, "third_right": 8_000_000}


class Rig:
    """Three bounded producers; no camera or hardware SDK is loaded."""

    def __init__(self, path, _config, _context, abort, *, pacing="original"):
        if pacing not in ("original", "uniform30"):
            raise ValueError("explicit supported replay pacing required")
        self.pacing = pacing
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
        # Fault the bounded replay fixture into cache before motion ownership.
        # This is replay preparation, not a claimed camera acquisition cost.
        for array in self.cache.arrays.values():
            array.reshape(-1).view("u1")[::4096].sum()
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
                due, frame = self.scheduled(role, sequence)
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

    def scheduled(self, role, sequence):
        """Separate actual source provenance from an explicit replay clock."""
        offset = (
            self.cache.due(role, sequence)
            if self.pacing == "original"
            else sequence * 1_000_000_000 // 30 + PHASE_NS[role]
        )
        due = self.started + offset
        frame = self.cache.frame(
            role, sequence, self.clock_id, due, self.started + self.offset
        )
        if self.pacing == "uniform30":
            depth_offset = frame.depth_timestamp_ns - frame.timestamp_ns
            frame = dataclasses.replace(
                frame,
                timestamp_ns=due + self.offset,
                depth_timestamp_ns=due + self.offset + depth_offset,
            )
        return due, frame

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


def configuration(path, pacing="original"):
    cache = Cache(path)
    try:
        config = cache.snapshot("probe", "fixture")["station"]
        return (
            config,
            functools.partial(Rig, path, pacing=pacing),
            {
                "cameras": {
                    "kind": "recorded_rgbd_replay",
                    "cache_sha256": cache.identity,
                    "frames_per_role": len(cache.groups),
                    "sequence_stride": cache.sequence_stride,
                    "wrist_sequences": [
                        cache.member("wrist", i)["color"]["sequence"]
                        for i in range(len(cache.groups))
                    ],
                    "cache_prefault_before_control": True,
                    "pacing": pacing,
                    "preserves_original_receipt_schedule": pacing == "original",
                    "synthetic_view_phase_ns": (
                        PHASE_NS if pacing == "uniform30" else None
                    ),
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
