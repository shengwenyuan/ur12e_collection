"""Concurrent real-camera recording and read-only leader load; no UR imports."""

import argparse
import json
import pathlib
import resource
import signal
import subprocess
import sys
import time

from ur12e_collection.leader import probe, source, stream


def run(args):
    """Preserve independent leader evidence throughout camera finalization."""
    args.output.mkdir(parents=True, exist_ok=False)
    reader = source.Reader(args.port, args.baudrate)
    timing, ages = probe.Timing(), []
    report = {"state": "running", "motor_writes": False, "ur_control": False}
    child = None
    started, cpu = time.monotonic(), time.process_time()
    try:
        reader.start()
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "ur12e_collection",
                "shadow",
                "--backend",
                "hardware",
                "--station",
                str(args.station),
                "--output",
                str(args.output / "cameras"),
                "--revision",
                args.revision,
                "--task",
                "read-only-load-120hz",
                "--episodes",
                str(args.episodes),
                "--seconds",
                str(args.seconds),
            ]
        )
        previous = None
        with (
            (args.output / "samples.jsonl").open("x") as trace,
            (args.output / "health.jsonl").open("x") as health,
        ):
            while child.poll() is None:
                if time.monotonic() - started > args.timeout:
                    raise TimeoutError("bounded load test exceeded deadline")
                view = reader.mailbox.view()
                if view.health != previous:
                    stream.write_health(view.health, health)
                    previous = view.health
                stream.write_samples(reader, trace, timing, ages)
                time.sleep(0.005)
            reader.close()
            stream.write_samples(reader, trace, timing, ages)
        if child.returncode:
            raise RuntimeError(f"camera worker exited {child.returncode}")
        report["state"] = "completed"
    except BaseException as error:
        report.update(state="failed", error=str(error) or type(error).__name__)
        raise
    finally:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                report["forced_camera_kill"] = True
        reader.close()
        elapsed = time.monotonic() - started
        report.update(
            timing.report(),
            elapsed_seconds=elapsed,
            nominal_hz=source.READ_HZ,
            cpu_cores=(time.process_time() - cpu) / elapsed,
            maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            delivery_age_ms=probe.distribution(ages),
            queue_peak=reader.mailbox.peak,
            traffic=reader.traffic,
            inventory=reader.inventory,
            epoch=reader.epoch,
            camera_exit=None if child is None else child.returncode,
        )
        (args.output / "leader-report.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=3000000)
    parser.add_argument("--station", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=40)
    parser.add_argument("--timeout", type=float, default=1500)
    print(json.dumps(run(parser.parse_args()), indent=2))
