"""Bounded persistent read-only evidence capture; no controller imports."""

import argparse
import dataclasses
import json
import pathlib
import resource
import time

from ur12e_collection.leader import probe, source


def run(
    device: str, baudrate: int, seconds: float, output: pathlib.Path
) -> dict:
    """Measure fresh acquisitions, host cost and consumer ages independently."""
    if not 0 < seconds <= 300:
        raise ValueError("capture duration must be within (0, 300] seconds")
    output.mkdir(parents=True, exist_ok=False)
    reader = source.Reader(device, baudrate)
    timing, ages = probe.Timing(), []
    report = {
        "state": "failed",
        "nominal_hz": source.READ_HZ,
        "baudrate": baudrate,
    }
    wall, cpu = time.monotonic(), time.process_time()
    try:
        reader.start()
        wall, cpu = time.monotonic(), time.process_time()
        _capture(reader, seconds, output, timing, ages)
        report["state"] = "completed"
    except (RuntimeError, OSError, KeyboardInterrupt) as error:
        report["error"] = str(error) or type(error).__name__
    finally:
        elapsed = time.monotonic() - wall
        cpu_seconds = time.process_time() - cpu
        reader.close()
        report.update(timing.report())
        report.update(
            elapsed_seconds=elapsed,
            cpu_seconds=cpu_seconds,
            cpu_cores=cpu_seconds / elapsed,
            maxrss_native_units=resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
            delivery_age_ms=probe.distribution(ages),
            queue_peak=reader.mailbox.peak,
            traffic=reader.traffic,
            inventory=reader.inventory,
            epoch=reader.epoch,
            health_hz=1,
            motion_ready=False,
        )
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _capture(reader, seconds, output, timing, ages):
    """Write acquired evidence and independently timestamped health."""
    deadline = time.monotonic() + seconds
    with (
        (output / "samples.jsonl").open("x", encoding="utf-8") as trace,
        (output / "health.jsonl").open("x", encoding="utf-8") as health_trace,
    ):
        previous_health = None
        try:
            while time.monotonic() < deadline:
                view = reader.mailbox.view()
                if view.health != previous_health:
                    write_health(view.health, health_trace)
                    previous_health = view.health
                write_samples(reader, trace, timing, ages)
                time.sleep(0.005)
        finally:
            reader.close()
            write_samples(reader, trace, timing, ages)


def write_samples(reader, trace, timing, ages):
    """Drain samples into the common calibration trace format."""
    for motion in reader.mailbox.drain():
        timing.add(motion.sample)
        ages.append((time.monotonic_ns() - motion.sample.start_ns) / 1e6)
        row = dataclasses.asdict(motion.sample)
        row["position"] = row.pop("raw")
        row["velocity_raw"] = motion.velocity_raw
        trace.write(json.dumps(row) + "\n")


def write_health(block, trace):
    """Preserve independently acquired torque and error timestamps."""
    trace.write(
        json.dumps(
            {
                "start_ns": block.start_ns,
                "end_ns": block.end_ns,
                "torque": block.integers(64, 1),
                "hardware_error": block.integers(70, 1),
                "errors": block.errors,
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = run(args.port, args.baudrate, args.seconds, args.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["state"] == "completed" else 1)
