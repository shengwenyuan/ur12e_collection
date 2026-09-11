"""Fault the new leader path during actual URSim following, then audit hold."""

import argparse
import dataclasses
import faulthandler
import json
import multiprocessing
import pathlib
import time

from session import press, tick, wait
from recording_faults import Factory
from ur12e_collection import synthetic
from ur12e_collection.simulation import connection, session
from ur12e_collection.simulation.leader import Trace


class FaultTrace(Trace):
    def __init__(self, path):
        super().__init__(path)
        self.fault = None
        self.frozen = None

    def samples(self, now_ns):
        if self.fault == "stale":
            return self.frozen
        values = super().samples(now_ns)
        self.frozen = values
        if self.fault == "epoch":
            return tuple(
                dataclasses.replace(value, epoch="injected-reset")
                for value in values
            )
        if self.fault == "range":
            return tuple(
                dataclasses.replace(value, raw=(100_000,) * 6 + (3256,))
                for value in values
            )
        return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--leader-trace", type=pathlib.Path, required=True)
    parser.add_argument("--leader-speed", type=float, default=1)
    parser.add_argument("--home-repeats", type=int, choices=range(1, 101))
    args = parser.parse_args()
    root = pathlib.Path("/results") / f"leader-faults-{time.time_ns()}"
    root.mkdir()
    report = {"status": "FAIL", "cases": []}
    try:
        faults = (
            "home_recorder",
            "stale",
            "epoch",
            "range",
            "recorder",
            "disk",
            "writer_backlog",
            "held_torque",
        )
        if args.home_repeats:
            faults = ("home_recorder",) * args.home_repeats
            faulthandler.dump_traceback_later(20, repeat=True)
        for index, fault in enumerate(faults):
            case = f"{fault}-{index:03d}" if args.home_repeats else fault
            trace = FaultTrace(args.leader_trace)
            trigger = multiprocessing.get_context("spawn").Event()
            camera_input = (
                (
                    synthetic.configuration(),
                    Factory(fault, trigger),
                    {"fault_fixture": fault},
                )
                if fault in ("disk", "writer_backlog")
                else None
            )
            with connection.open_station() as station:
                active = session.create(
                    station,
                    root / case,
                    inputs=session.Inputs(trace, camera_input),
                )
                try:
                    if fault == "home_recorder":
                        motors = trace.motor_fixture
                        motors.value = dataclasses.replace(
                            motors.value,
                            counts=(
                                motors.value.counts[0] - 400,
                                *motors.value.counts[1:],
                            ),
                        )
                    press(active)
                    if fault == "home_recorder":
                        deadline = time.monotonic() + 3
                        while active.setup.companion.phase != "homing":
                            assert time.monotonic() < deadline
                            tick(active)
                        assert motors.value.counts != tuple(motors.goal)
                    else:
                        wait(active, "ready")
                        press(active)
                        wait(active, "recording")
                        until = time.monotonic() + 7
                        while time.monotonic() < until:
                            tick(active)
                    if fault == "held_torque":
                        press(active)
                        wait(active, "held")
                    retained = len(active.completed)
                    started = time.monotonic()
                    if fault in ("recorder", "home_recorder"):
                        active.recorder.process.kill()
                    elif fault in ("disk", "writer_backlog"):
                        trigger.set()
                    elif fault == "held_torque":
                        trace.motor_fixture.value = dataclasses.replace(
                            trace.motor_fixture.value, torque=(False,) * 7
                        )
                    else:
                        trace.fault = fault
                    error = None
                    while time.monotonic() - started < 2:
                        try:
                            tick(active)
                        except Exception as exception:
                            error = str(exception)
                            break
                    assert error and active.state == "fault"
                    assert len(active.completed) == retained
                    if fault == "disk":
                        assert "disk full" in error
                    elif fault == "writer_backlog":
                        assert "queue overflow" in error
                    elif fault == "held_torque":
                        assert "leader" in error and retained == 1
                    elif fault == "home_recorder":
                        assert "recorder" in error
                        assert active.setup.companion.phase == "holding"
                        assert tuple(motors.goal) == motors.value.counts
                        assert (
                            motors.value.counts
                            != active.setup.companion.motion.home
                        )
                        assert all(motors.value.torque)
                    fault_and_release_s = time.monotonic() - started
                    samples = []
                    until = time.monotonic() + 3
                    while time.monotonic() < until:
                        state = station.read()
                        samples.append(dataclasses.asdict(state))
                        time.sleep(0.02)
                    tail = samples[-50:]
                    assert (
                        max(abs(v) for state in tail for v in state["qd"])
                        < 0.001
                    )
                    assert all(
                        abs(a - b) < 0.001
                        for state in tail
                        for a, b in zip(state["q"], tail[0]["q"])
                    )
                    assert (
                        len(
                            list(
                                (root / case).glob(
                                    "episode-[0-9][0-9][0-9][0-9]/metadata.json"
                                )
                            )
                        )
                        == retained
                    )
                    (root / f"{case}-feedback.json").write_text(
                        json.dumps(samples)
                    )
                    report["cases"].append(
                        {
                            "fault": fault,
                            "case": case,
                            "status": "PASS",
                            "error": error,
                            "fault_and_release_s": fault_and_release_s,
                            "hold_observation_s": 3,
                            "prior_complete_episodes_retained": retained,
                        }
                    )
                finally:
                    active.close()
            print(json.dumps(report["cases"][-1]), flush=True)
        report["status"] = "PASS"
    except BaseException as error:
        report["error"] = repr(error)
        raise
    finally:
        (root / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
