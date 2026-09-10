"""Independent recording process with bounded control-watermark admission."""

import collections
import multiprocessing
import pathlib
import queue
import time

from ur12e_collection import (
    contracts,
    rig,
    session,
    shared_frames,
    snapshots,
    verification,
    workers,
)

HEARTBEAT_NS = 500_000_000
HANDOVER_NS = 3_000_000_000
CAPACITY = 32


class _Capture:
    """Keep camera delivery separate from the active control receipt window."""

    def __init__(self, source, owner):
        self.source, self.owner = source, owner
        self.pending = collections.deque()
        self.watermark = 0
        self.cutoff = None
        self.release = None
        self.settled = False
        self.prepared_ack = False
        self.timings = collections.Counter()

    def message(self, operation, value):
        """Apply ordered ownership messages before admitting buffered frames."""
        if operation == "prepare":
            self.owner.prepare(pathlib.Path(value))
            self.prepared_ack = False
        elif operation == "begin":
            boundary, event = value
            self.owner.begin(boundary)
            self.owner.submit_feedback([event])
            self.watermark, self.cutoff, self.release = boundary, None, None
            self.pending.clear()
            self.settled = False
        elif operation == "samples":
            watermark, records = value
            if self.owner.state != "recording" or self.cutoff is not None:
                raise RuntimeError("samples require active recording")
            if watermark <= self.watermark:
                raise RuntimeError("control watermark did not advance")
            if any(
                r.provenance.time.received_monotonic_ns >= watermark
                for r in records
            ):
                raise RuntimeError("sample exceeds control watermark")
            self.owner.submit_feedback(records)
            self.watermark = watermark
        elif operation == "stop":
            cutoff, event = value
            if self.owner.state != "recording" or cutoff < self.watermark:
                raise RuntimeError("stop precedes admitted control watermark")
            self.watermark, self.cutoff, self.release = cutoff, cutoff, event
        elif operation == "settled":
            if self.cutoff is None:
                raise RuntimeError("stop confirmation has no cutoff")
            self.settled = True
        else:
            raise ValueError("unknown recording operation")

    def step(self, now_ns=None):
        """Drain sources continuously, including idle and codec finalization."""
        entered = time.monotonic_ns()
        frames = self.source.read()
        read_ns = time.monotonic_ns()
        self.timings["max_read_ms"] = max(
            self.timings["max_read_ms"], (read_ns - entered) / 1e6
        )
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        for frame in frames:
            receipt = frame.color.time.received_monotonic_ns
            if self.owner.state == "recording":
                if self.cutoff is None or receipt < self.cutoff:
                    self.pending.append(frame)
            elif self.owner.state == "finalizing":
                self.owner.submit(frame, now_ns)
        waiting = collections.deque()
        while self.pending:
            frame = self.pending.popleft()
            receipt = frame.color.time.received_monotonic_ns
            if receipt < self.watermark:
                self.owner.submit(frame, now_ns)
            elif self.cutoff is None:
                waiting.append(frame)
        self.pending = waiting
        if len(waiting) > CAPACITY:
            raise RuntimeError("control-watermark camera buffer overflow")
        self.owner.advance(now_ns)
        if self.cutoff is not None and self.owner.state == "recording":
            if (
                self.settled
                and now_ns >= self.cutoff + self.owner.config.wait_ns
            ):
                self.owner.submit_feedback([self.release])
                self.owner.stop(now_ns, cutoff_ns=self.cutoff)
        report = self.owner.poll()
        self.timings["max_admit_ms"] = max(
            self.timings["max_admit_ms"], (time.monotonic_ns() - read_ns) / 1e6
        )
        if report is not None:
            report["capture_timings"] = dict(self.timings)
            report["sources"] = self.source.statistics()
        return report


def _worker(config, context, channels):
    _, replies, abort, _, slots = channels
    source = rig.Rig(
        config,
        "synthetic" if context["simulated"] else "hardware",
        queue_capacity=context["control"]["camera_queue_capacity"],
        shared_slots=slots,
        stop=abort,
    )
    owner = capture_owner = verifier = None
    try:
        verifier = verification.Verifier(abort)
        source.start()
        snapshot = snapshots.build(
            config,
            source.observations,
            context
            | {
                "clock_id": source.clock_id,
            },
        )
        owner = session.Session.from_snapshot(snapshot, verify=verifier.verify)
        capture_owner = _Capture(source, owner)
        replies.put_nowait(("ready", snapshot))
        _run(capture_owner, channels)
    # The child must report SDK/codec failures before aborting its partial.
    # pylint: disable-next=broad-exception-caught
    except (Exception, KeyboardInterrupt) as error:
        print(f"recorder worker failed: {error!r}", flush=True)
        if capture_owner is not None:
            print(f"capture timings: {dict(capture_owner.timings)}", flush=True)
        print(f"source statistics: {source.statistics()}", flush=True)
        if owner is not None:
            if owner.writer is not None:
                print(f"writer health: {owner.writer.health()}", flush=True)
            owner.abort()
        try:
            replies.put_nowait(("error", str(error)))
        except queue.Full:
            pass
    finally:
        abort.set()
        try:
            if owner is not None:
                owner.close()
        finally:
            try:
                source.close()
            finally:
                if verifier is not None:
                    verifier.close()
                replies.cancel_join_thread()


def _run(capture_owner, channels):
    commands, replies, abort, pulse, _ = channels
    contacted = sent = time.monotonic_ns()
    while not abort.is_set():
        now = time.monotonic_ns()
        for _ in range(CAPACITY):
            try:
                operation, value = commands.get_nowait()
            except queue.Empty:
                break
            contacted = now
            if operation != "heartbeat":
                capture_owner.message(operation, value)
                if operation == "begin":
                    replies.put_nowait((operation, None))
        if capture_owner.owner.state in (
            "prepared",
            "recording",
            "finalizing",
        ) and now - contacted > (
            HANDOVER_NS if capture_owner.settled else HEARTBEAT_NS
        ):
            raise RuntimeError("recording owner heartbeat lost")
        report = capture_owner.step()
        owner = capture_owner.owner
        if (
            owner.state == "prepared"
            and not capture_owner.prepared_ack
            and owner.writer.health()["initialized"]
        ):
            replies.put_nowait(("prepare", None))
            capture_owner.prepared_ack = True
        if report is not None:
            replies.put_nowait(("complete", report))
        if now - sent >= 100_000_000:
            pulse.value = now
            sent = now
        time.sleep(0.001)


class Recorder:
    """Nonblocking control-side IPC; queue loss is a session fault."""

    def __init__(self, config: dict, context: dict):
        ctx = multiprocessing.get_context("spawn")
        self.commands, self.replies = ctx.Queue(CAPACITY), ctx.Queue(CAPACITY)
        self.abort = ctx.Event()
        self.pulse = ctx.Value("q", 0)
        self.slots = {}
        try:
            if context["control"].get("camera_transport") == "shared_memory":
                for role in contracts.CAMERA_ROLES:
                    self.slots[role] = shared_frames.Slots.create(
                        ctx, context["control"]["camera_queue_capacity"]
                    )
        except BaseException:
            for slots in self.slots.values():
                slots.close()
            raise
        self.process = ctx.Process(
            target=_worker,
            args=(
                config,
                context,
                (
                    self.commands,
                    self.replies,
                    self.abort,
                    self.pulse,
                    {
                        role: slots.descriptor()
                        for role, slots in self.slots.items()
                    },
                ),
            ),
            name="episode-recorder",
        )
        self.last_reply = self.last_heartbeat = 0
        self.ready = False

    def start(self) -> dict:
        """Initialize before acquiring SDK control; startup may take seconds."""
        self.process.start()
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            for operation, value in self.poll():
                if operation == "ready":
                    self.ready = True
                    return value
            time.sleep(0.01)
        raise TimeoutError("recorder startup timed out")

    def send(self, operation: str, value=None) -> None:
        """Never wait for camera/encoder work in the control loop."""
        try:
            self.commands.put_nowait((operation, value))
        except queue.Full as error:
            raise RuntimeError("recording command queue overflow") from error

    def poll(self) -> list:
        """Check health, refresh ownership and drain reliable replies."""
        now = time.monotonic_ns()
        result = []
        while True:
            try:
                operation, value = self.replies.get_nowait()
            except queue.Empty:
                break
            self.last_reply = now
            if operation == "error":
                raise RuntimeError(f"recorder failed: {value}")
            if operation != "heartbeat":
                result.append((operation, value))
        self.last_reply = max(self.last_reply, self.pulse.value)
        if not self.process.is_alive():
            raise RuntimeError("recorder process exited")
        if self.ready and now - self.last_reply > HEARTBEAT_NS:
            raise RuntimeError("recorder status is stale")
        if self.ready and now - self.last_heartbeat >= 100_000_000:
            self.send("heartbeat")
            self.last_heartbeat = now
        return result

    def close(self) -> None:
        """Revoke unfinished commits and reap the child without new motion."""
        self.abort.set()
        if self.process.pid is not None:
            workers.stop(self.process)
        for slots in self.slots.values():
            slots.close()
        self.slots.clear()
        for channel in (self.commands, self.replies):
            channel.cancel_join_thread()
            channel.close()
