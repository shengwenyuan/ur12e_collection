"""One passive guided leader session; motion assessment happens offline."""

import argparse
import json
import pathlib
import subprocess
import time

from ur12e_collection.leader import probe, source, stream

NAMES = ("base", "shoulder", "elbow", "wrist one", "wrist two", "wrist three")


def phases() -> list[dict]:
    """Fixed labels make one recorded session analyzable without chat timing."""
    result = []

    def add(name, seconds, cue, motor=None):
        start = result[-1]["end_s"] if result else 0
        result.append(
            {
                "name": name,
                "start_s": start,
                "end_s": start + seconds,
                "motor": motor,
                "cue": cue,
            }
        )

    add("reference_start", 5, "Reference. Hold still.")
    for motor, name in enumerate(NAMES, 1):
        for suffix, cue in (
            ("move_a", f"{name}. A, counterclockwise."),
            ("hold_a", "Hold A."),
            ("move_b", "B, clockwise past the reference."),
            ("hold_b", "Hold B."),
            ("return_b", "Return to reference."),
        ):
            add(f"j{motor}_{suffix}", 4, cue, motor)
    for name, cue in (
        ("lever_move_open", "Lever counterclockwise. Open."),
        ("gripper_open_0", "Hold open."),
        ("lever_move_closed", "Lever clockwise. Closed."),
        ("gripper_closed_0", "Hold closed."),
        ("lever_return", "Return lever to reference."),
    ):
        add(name, 4, cue, 7)
    add("reference_end", 5, "Final reference. Hold still.")
    return result


class Guide:
    """Only emit timed cues and record their actual emission times."""

    def __init__(self, schedule, start_ns, output, speak=False):
        self.schedule = schedule
        self.start_ns = start_ns
        self.output = output
        self.speak = speak
        self.index = 0
        self.voice = None

    def tick(self, now_ns):
        """Reject late prompts instead of shifting the labelled actions."""
        if self.index >= len(self.schedule):
            return
        phase = self.schedule[self.index]
        due = self.start_ns + int(phase["start_s"] * 1e9)
        if now_ns < due:
            return
        if now_ns - due > 500_000_000:
            raise RuntimeError("guidance cue delayed over 500 ms")
        self.output.write(json.dumps(phase | {"cue_ns": now_ns}) + "\n")
        self.output.flush()
        print(f"\a[{phase['start_s']:3}s] {phase['cue']}", flush=True)
        if self.speak:
            self.close()
            # The guide owns speech across ticks; close() reaps it.
            self.voice = (
                subprocess.Popen(  # pylint: disable=consider-using-with
                    ["/usr/bin/say", "-r", "230", phase["cue"]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        self.index += 1

    def close(self):
        """Stop only our optional speech process; never alter motor state."""
        if self.voice is not None:
            if self.voice.poll() is None:
                self.voice.terminate()
            self.voice.wait(timeout=2)
            self.voice = None


def capture(device, baudrate, output, *, speak=False, home_declared=False):
    """Capture once with passive torque checks and no calibration activation."""
    if speak and not pathlib.Path("/usr/bin/say").is_file():
        raise ValueError("speech option requires macOS say")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "state": "failed",
        "nominal_hz": source.READ_HZ,
        "baudrate": baudrate,
        "operator_declared_home": home_declared,
        "motion_ready": False,
        "protocol": "passive_150s_v3",
        "gripper_convention": "output_shaft_view_ccw_open_cw_closed",
    }
    reader = source.Reader(device, baudrate)
    timing, ages = probe.Timing(), []
    try:
        reader.start()
        if any(row["torque"] for row in reader.inventory.values()):
            raise RuntimeError("manual calibration requires torque off")
        schedule = phases()
        report.update(start_ns=time.monotonic_ns(), phases=schedule)
        (output / "schedule.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        _capture(reader, output, report, timing, ages, speak=speak)
        report["state"] = "completed"
        print(
            "Capture complete. Support the arm. No motor writes were sent.",
            flush=True,
        )
    except (RuntimeError, OSError, KeyboardInterrupt) as error:
        report["error"] = str(error) or type(error).__name__
        print(
            f"CAPTURE STOPPED: {report['error']}. Keep the arm supported.",
            flush=True,
        )
    finally:
        reader.close()
        report.update(timing.report())
        report.update(
            inventory=reader.inventory,
            traffic=reader.traffic,
            epoch=reader.epoch,
            queue_peak=reader.mailbox.peak,
            delivery_age_ms=probe.distribution(ages),
        )
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _capture(reader, output, report, timing, ages, *, speak):
    # Separate files preserve sensor and cue clocks without resampling.
    # pylint: disable=too-many-arguments
    with (
        (output / "samples.jsonl").open("x") as trace,
        (output / "events.jsonl").open("x") as events,
        (output / "health.jsonl").open("x") as health_trace,
    ):
        guide = Guide(report["phases"], report["start_ns"], events, speak)
        previous = None
        end = report["start_ns"] + int(report["phases"][-1]["end_s"] * 1e9)
        try:
            while time.monotonic_ns() < end:
                view = reader.mailbox.view()
                if view.health != previous:
                    stream.write_health(view.health, health_trace)
                    health_trace.flush()
                    previous = view.health
                if any(view.health.integers(64, 1)):
                    raise RuntimeError(
                        "torque enabled during passive calibration"
                    )
                guide.tick(time.monotonic_ns())
                stream.write_samples(reader, trace, timing, ages)
                trace.flush()
                time.sleep(0.005)
        finally:
            reader.close()
            stream.write_samples(reader, trace, timing, ages)
            guide.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--speak", action="store_true")
    parser.add_argument("--home-declared", action="store_true")
    args = parser.parse_args()
    value = capture(
        args.port,
        args.baudrate,
        args.output,
        speak=args.speak,
        home_declared=args.home_declared,
    )
    raise SystemExit(0 if value["state"] == "completed" else 1)
