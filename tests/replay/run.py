"""Paced three-view replay through the production camera session and writer."""

import argparse
import dataclasses
import json
import pathlib
import queue
import resource
import threading
import time
import uuid

from feed import Cache
from ur12e_collection import contracts, session
from ur12e_collection.leader import probe


class Feeder:
    """Three independent producers, each with eight owned-frame slots."""

    def __init__(self, cache, snapshot, seconds):
        self.cache = cache
        self.snapshot = snapshot
        self.duration_ns = int(seconds * 1e9)
        self.start_ns = time.monotonic_ns() + 200_000_000
        self.unix_ns = time.time_ns() + 200_000_000
        self.stop = threading.Event()
        self.queues = {role: queue.Queue(8) for role in contracts.CAMERA_ROLES}
        self.stats = {
            role: {"frames": 0, "queue_peak": 0, "error": None}
            for role in contracts.CAMERA_ROLES
        }
        self.threads = [
            threading.Thread(target=self._worker, args=(r,), name=f"replay-{r}")
            for r in contracts.CAMERA_ROLES
        ]

    def _worker(self, role):
        sequence = 0
        try:
            while not self.stop.is_set():
                due = self.start_ns + self.cache.due(role, sequence)
                if due >= self.start_ns + self.duration_ns:
                    break
                # Prefetch one owned frame before its delivery deadline.
                frame = self.cache.frame(
                    role,
                    sequence,
                    self.snapshot["clock_id"],
                    due,
                    self.unix_ns,
                )
                if self.stop.wait(max(0, (due - time.monotonic_ns()) / 1e9)):
                    break
                receipt = time.monotonic_ns()
                frame = dataclasses.replace(
                    frame,
                    **{
                        kind: dataclasses.replace(
                            getattr(frame, kind),
                            time=dataclasses.replace(
                                getattr(frame, kind).time,
                                received_monotonic_ns=receipt,
                            ),
                        )
                        for kind in ("color", "depth")
                    },
                )
                self.queues[role].put_nowait((frame, sequence, due))
                self.stats[role]["frames"] += 1
                self.stats[role]["queue_peak"] = max(
                    self.stats[role]["queue_peak"], self.queues[role].qsize()
                )
                sequence += 1
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.stats[role]["error"] = f"{type(error).__name__}: {error}"
            self.stop.set()

    def start(self):
        """Start producers only after the episode writer is prepared."""
        for thread in self.threads:
            thread.start()

    def capture(self, owner, output):
        """Drain views fairly and fail without disguising missing frames."""
        delays = []
        with (output / "schedule.jsonl").open("x", encoding="utf-8") as trace:
            while any(t.is_alive() for t in self.threads) or any(
                not q.empty() for q in self.queues.values()
            ):
                for role, channel in self.queues.items():
                    if self.stats[role]["error"]:
                        raise RuntimeError(self.stats[role]["error"])
                    try:
                        frame, sequence, due = channel.get_nowait()
                    except queue.Empty:
                        continue
                    now = time.monotonic_ns()
                    owner.submit(frame, now)
                    delays.append((now - due) / 1e6)
                    trace.write(
                        json.dumps(
                            {
                                "role": role,
                                "sequence": sequence,
                                "due_ns": due,
                                "submitted_ns": now,
                            }
                        )
                        + "\n"
                    )
                owner.advance(time.monotonic_ns())
                owner.poll()
                time.sleep(0.001)
        if any(s["error"] for s in self.stats.values()):
            raise RuntimeError("replay producer failed")
        return probe.distribution(delays)

    def close(self):
        """Stop producers before closing their memory maps."""
        self.stop.set()
        for thread in self.threads:
            if thread.ident is not None:
                thread.join(5)
            if thread.is_alive():
                raise TimeoutError("replay producer did not close")


def run(cache_path, output, seconds, revision):
    """Re-encode raw images and independently verify the final archive."""
    if not 0 < seconds <= 120:
        raise ValueError("replay duration must be within (0, 120] seconds")
    output.mkdir(parents=True, exist_ok=False)
    cache = Cache(cache_path)
    snapshot = cache.snapshot(uuid.uuid4().hex, revision)
    (output / "source-manifest.json").write_text(
        json.dumps(cache.manifest) + "\n"
    )
    owner = session.Session.from_snapshot(snapshot)
    feeder = None
    report = {
        "state": "failed",
        "simulated_camera_replay": True,
        "physical_leader_in_archive": False,
    }
    wall, cpu = time.monotonic(), time.process_time()
    try:
        owner.prepare(output / "episode-0000")
        deadline = time.monotonic() + 10
        while not owner.writer.health()["initialized"]:
            owner.poll()
            if time.monotonic() >= deadline:
                raise TimeoutError("writer did not initialize")
            time.sleep(0.005)
        feeder = Feeder(cache, snapshot, seconds)
        owner.begin(feeder.start_ns)
        feeder.start()
        report["delivery_delay_ms"] = feeder.capture(owner, output)
        report["capture_cpu_cores"] = (time.process_time() - cpu) / (
            time.monotonic() - wall
        )
        report["capture_seconds"] = time.monotonic() - wall
        report["source"] = feeder.stats
        report["writer_before_stop"] = owner.writer.health()
        owner.stop(time.monotonic_ns())
        deadline = time.monotonic() + 120
        result = None
        while result is None and time.monotonic() < deadline:
            result = owner.poll()
            time.sleep(0.01)
        if result is None:
            raise TimeoutError("archive verification did not finish")
        report.update(state="completed", result=result)
    except Exception as error:  # pylint: disable=broad-exception-caught
        report["error"] = f"{type(error).__name__}: {error}"
        if owner.writer is not None:
            report["writer_on_failure"] = owner.writer.health()
        if feeder is not None:
            report["source"] = feeder.stats
    finally:
        if feeder is not None:
            feeder.close()
        owner.close()
        cache.close()
        report["elapsed_seconds"] = time.monotonic() - wall
        report["maxrss_native_units"] = resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--seconds", type=float, default=40)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    value = run(args.cache, args.output, args.seconds, args.revision)
    print(json.dumps(value, indent=2))
    raise SystemExit(0 if value["state"] == "completed" else 1)
