"""Live physical encoder input; motion ownership stays inside isolated URSim."""

import collections
import multiprocessing
import queue
import json
import pathlib
import time

from ur12e_collection import workers
from ur12e_collection.leader import episode, mapping
from ur12e_collection.leader import input as leader_input
from ur12e_collection.simulation import bridge, profile


class Feed:
    """Keep acquisition timing and refuse stale or restarted publishers."""

    def __init__(self, root: pathlib.Path, calibration: pathlib.Path):
        self.root = root
        self.calibration = mapping.from_document(
            json.loads(calibration.read_text())
        )
        if self.calibration.home_rad != profile.HOME:
            raise ValueError("calibration and simulator HOME differ")
        self.clock = bridge.Clock(root)
        self.clock.synchronize()
        self.epoch = None
        self.previous = None
        self.recent = collections.deque(maxlen=16)
        self.origin = {
            "kind": "physical_live_leader",
            "transport": "local_atomic_file",
            "motor_writes": False,
            "physical_direction_verified": False,
            "host_to_owner_offset_ns": self.clock.bounds[0],
            "clock_uncertainty_ns": self.clock.bounds[1] - self.clock.bounds[0],
            "holding": "operator_support_no_motor_commands",
        }

    def samples(self, now_ns):
        """Keep cache identity and the original acquisition time."""
        self.clock.check(now_ns)
        value = bridge.read(self.root / "latest.json")
        if not value or value.get("fault"):
            raise ValueError(f"live leader unavailable: {value}")
        observed_ns = max(now_ns, time.monotonic_ns())
        offset = self.clock.bounds[0]
        age_ns = observed_ns - (value["published_ns"] + offset)
        if not 0 <= age_ns <= 100_000_000:
            raise ValueError(
                "live leader publication stale or future: "
                f"age_ms={age_ns / 1e6:.3f}, bounds={self.clock.bounds}"
            )
        self._health(value, observed_ns, offset)
        if self.epoch is not None and value["epoch"] != self.epoch:
            raise ValueError("live leader epoch changed")
        self.epoch = value["epoch"]
        if not 1 <= len(value["samples"]) <= 16:
            raise ValueError("live leader window size invalid")
        if (
            self.previous
            and value["samples"][-1]["sequence"] < self.previous.sequence
        ):
            raise ValueError("live leader file reordered")
        for row in value["samples"]:
            self._append(row, observed_ns, offset)
        # A publish may race the file read. Return an as-of-call view without
        # relabeling new acquisitions or mistaking them for a future clock.
        available = tuple(
            s
            for s in self.recent
            if s.end_ns <= now_ns and observed_ns - s.start_ns <= 100_000_000
        )
        if not available:
            raise ValueError(
                "live leader acquisition stale: "
                f"call_to_read_ms={(observed_ns-now_ns)/1e6:.3f}, "
                f"start_age_ms={(observed_ns-self.previous.start_ns)/1e6:.3f}, "
                f"end_vs_call_ms={(self.previous.end_ns-now_ns)/1e6:.3f}"
            )
        return available

    @staticmethod
    def _health(value, now_ns, offset):
        """Health is independently acquired and must remain torque-off."""
        if not (
            value["health_start_ns"] <= value["health_end_ns"]
            and 0 <= now_ns - (value["health_end_ns"] + offset)
            and now_ns - (value["health_start_ns"] + offset) <= 2_000_000_000
        ):
            raise ValueError("live leader health expired or future")
        for key in ("torque", "hardware_error", "health_errors"):
            if len(value[key]) != 7 or any(value[key]):
                raise ValueError("live leader torque or hardware status unsafe")

    def _append(self, row, now_ns, offset):
        """Merge only new consecutive acquisitions into the bounded window."""
        sample = episode.Sample(
            row["epoch"],
            row["sequence"],
            row["start_ns"] + offset,
            row["end_ns"] + offset,
            tuple(row["raw"]),
            tuple(row["errors"]),
        )
        if sample.epoch != self.epoch:
            raise ValueError("live leader sample epoch differs")
        if self.previous and sample.sequence <= self.previous.sequence:
            if (
                sample.sequence == self.previous.sequence
                and sample != self.previous
            ):
                raise ValueError("live leader cached sample changed")
            return
        if self.previous:
            if sample.sequence != self.previous.sequence + 1:
                raise ValueError("live leader sequence gap")
            episode.check_advance(self.previous, sample, 100_000_000)
        if sample.end_ns > now_ns:
            raise ValueError("live leader acquisition is in the future")
        self.recent.append(sample)
        self.previous = sample


def _receive(root, calibration, samples, status, stop):
    """Own file IO in a process isolated from native SDK/GIL pauses."""
    workers.ignore_terminal_interrupt()
    try:
        feed = Feed(root, calibration)
        status.send(("ready", feed.origin))
        while not stop.is_set():
            values = feed.samples(time.monotonic_ns())
            try:
                samples.get_nowait()
            except queue.Empty:
                pass
            try:
                samples.put_nowait(values)
            except queue.Full:
                pass  # Retain one already queued, timestamped control view.
            stop.wait(0.002)
    except Exception as error:  # pylint: disable=broad-exception-caught
        status.send(("error", str(error)))
    finally:
        samples.cancel_join_thread()
        samples.close()
        status.close()


class Live:
    """Bounded latest views, independent of blocking simulator handovers."""

    def __init__(self, root, calibration):
        self.calibration = mapping.load(calibration)
        context = multiprocessing.get_context("spawn")
        self.stop = workers.Cancellation(context)
        self.views = context.Queue(maxsize=1)
        self.status, self.child = context.Pipe(duplex=False)
        self.process = context.Process(
            target=_receive,
            args=(root, calibration, self.views, self.child, self.stop),
            name="live-leader",
            daemon=True,
        )
        self.origin, self.view = None, ()

    def __enter__(self):
        self.process.start()
        self.child.close()
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                self._read()
                if self.origin is not None and self.view:
                    self.samples(time.monotonic_ns())
                    return self
                time.sleep(0.002)
            raise ValueError("live leader bridge did not become ready")
        except BaseException:
            self.__exit__()
            raise

    def _read(self):
        while self.status.poll():
            try:
                kind, value = self.status.recv()
            except EOFError as error:
                raise ValueError("live leader worker exited") from error
            if kind == "error":
                raise ValueError(f"live leader bridge stopped: {value}")
            self.origin = value
        if self.stop.is_set() or not self.process.is_alive():
            raise ValueError("live leader bridge stopped")
        try:
            self.view = self.views.get_nowait()
        except queue.Empty:
            pass

    def samples(self, now_ns):
        """Detach a fresh cached view without disk IO on the control loop."""
        self._read()
        values = tuple(
            s
            for s in self.view
            if s.end_ns <= now_ns and now_ns - s.start_ns <= 100_000_000
        )
        if not values:
            raise ValueError("live leader bridge acquisition stale")
        return values

    def __exit__(self, *_args):
        self.stop.set()
        workers.stop(self.process)
        self.status.close()
        self.views.close()
        self.views.join_thread()

    def companion(self):
        """Manual support replaces a motor HOME/HOLD companion."""
        return None

    def factory(self, limits):
        """Inject the shared relative mapper and conditioner."""

        def create(follower, now_ns):
            return leader_input.Input(
                self, self.calibration, limits, follower, now_ns
            )

        return create
