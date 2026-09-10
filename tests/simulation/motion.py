"""URSim-only motion acceptance with actual feedback and retained failures."""

import dataclasses
import json
import pathlib
import time

from ur12e_collection.control.backends import open_backend
from ur12e_collection.control.model import distance
from ur12e_collection.control.owner import Controller
from ur12e_collection.simulation import profile
from ur12e_collection.simulation.targets import Wave


def tick(control, samples):
    started = time.monotonic()
    state = control.tick(time.monotonic_ns())
    samples.append(dataclasses.asdict(state))
    time.sleep(max(0.0, profile.PERIOD - (time.monotonic() - started)))
    return state


def wait_hold(control, samples):
    while control.state != "hold":
        tick(control, samples)


def hold_gate(control, samples):
    requested = time.monotonic()
    control.halt(time.monotonic_ns())
    wait_hold(control, samples)
    elapsed = time.monotonic() - requested
    anchor = control.progress.feedback.q
    drift = 0.0
    end = time.monotonic() + 1.0
    while time.monotonic() < end:
        feedback = tick(control, samples)
        drift = max(drift, distance(anchor, feedback.q))
        assert max(map(abs, feedback.qd)) < 0.01
    assert elapsed < 1.0, elapsed
    assert drift < 0.01, drift
    return {"stop_seconds": elapsed, "hold_drift_rad": drift}


def run():
    samples, results = [], {}
    path = pathlib.Path("/results") / f"motion-{time.time_ns()}.json"
    try:
        with open_backend("ursim") as transport:
            control = Controller(transport, profile.LIMITS, "simulation-wave")
            tick(control, samples)
            control.go_ready(time.monotonic_ns())
            wait_hold(control, samples)
            results["initial_home_error_rad"] = distance(
                control.progress.feedback.q, profile.HOME
            )
            poses = (
                (0.7, -1.2, -1.9, -0.9, 1.1, -0.7),
                (4.0, -2.0, -0.9, -1.3, 1.8, 4.1),
                (-4.0, -1.1, -2.1, -1.9, 1.1, -4.1),
                (-5.3, -2.8, -0.3, -1.1, 2.7, -5.2),
                (3.6, -0.6, -2.7, -1.8, 0.7, 5.2),
                profile.HOME,
            )
            errors = []
            for pose in poses:
                control.route(
                    (pose,), control.progress.feedback.q, time.monotonic_ns()
                )
                wait_hold(control, samples)
                error = distance(control.progress.feedback.q, pose)
                assert error < 0.01, error
                errors.append(error)
                print(
                    json.dumps({"pose_reached": pose, "error": error}),
                    flush=True,
                )
            results["complex_pose_errors_rad"] = errors
            control.route(
                (poses[0], poses[1]),
                control.progress.feedback.q,
                time.monotonic_ns(),
            )
            until = time.monotonic() + 0.4
            while time.monotonic() < until:
                tick(control, samples)
            results["stop_move"] = hold_gate(control, samples)
            control.go_ready(time.monotonic_ns())
            ready_begin = len(samples)
            wait_hold(control, samples)
            peak = max(
                abs(qd)
                for sample in samples[ready_begin:]
                for qd in sample["qd"]
            )
            assert peak <= profile.LIMITS.ready_speed + 0.02, peak
            results["ready_peak_speed_rad_s"] = peak
            wave = Wave(control.progress.feedback.q, time.monotonic_ns())
            control.engage(
                wave.sample(time.monotonic_ns()), time.monotonic_ns()
            )
            until = time.monotonic() + 12.0
            tracking = []
            while time.monotonic() < until:
                started = time.monotonic()
                state = control.tick(time.monotonic_ns())
                samples.append(dataclasses.asdict(state))
                target = wave.sample(time.monotonic_ns())
                control.follow(target, time.monotonic_ns())
                tracking.append(distance(target.q, state.q))
                time.sleep(
                    max(0.0, profile.PERIOD - (time.monotonic() - started))
                )
            results["stream_max_tracking_error_rad"] = max(tracking)
            results["stop_servo"] = hold_gate(control, samples)
            control.go_ready(time.monotonic_ns())
            wait_hold(control, samples)
            results["status"] = "PASS"
            control.close()
    except Exception as error:
        results.update(status="FAIL", error=str(error))
        raise
    finally:
        path.write_text(
            json.dumps({"results": results, "samples": samples}),
            encoding="utf-8",
        )
        print(json.dumps({"report": str(path), **results}), flush=True)


if __name__ == "__main__":
    run()
