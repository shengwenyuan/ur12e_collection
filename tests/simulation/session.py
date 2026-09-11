"""Actual URSim control with persistent synthetic RGB-D recording acceptance."""

import argparse
import json
import pathlib
import time
import traceback

from ur12e_collection import mcap_read, storage, timing
from acceptance import decisions
from ur12e_collection.simulation import connection, session


def tick(owner):
    deadline = getattr(owner, "test_deadline_ns", time.monotonic_ns())
    owner.step()
    period = round(1e9 / owner.snapshot["control"]["control_hz"])
    owner.test_deadline_ns = timing.next_deadline(
        deadline, time.monotonic_ns(), period
    )
    time.sleep(max(0, (owner.test_deadline_ns - time.monotonic_ns()) / 1e9))


def wait(owner, expected, timeout=60):
    deadline = time.monotonic() + timeout
    while owner.state != expected:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"session did not reach {expected}: {owner.state}"
            )
        tick(owner)


def press(owner, key=" "):
    # Distinct user presses; the unit gate separately exercises key repeat.
    until = time.monotonic() + 0.3
    while time.monotonic() < until:
        tick(owner)
    owner.key(key, time.monotonic_ns())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--ros-observe", action="store_true")
    parser.add_argument("--kill-observer", action="store_true")
    parser.add_argument("--leader-trace", type=pathlib.Path)
    parser.add_argument("--leader-speed", type=float, default=1.0)
    parser.add_argument("--camera-cache", type=pathlib.Path)
    parser.add_argument(
        "--camera-pacing", choices=("original", "uniform30"), default="original"
    )
    args = parser.parse_args()
    camera_input = None
    if args.camera_cache:
        from replay.rig import configuration

        camera_input = configuration(args.camera_cache, args.camera_pacing)
    trace = None
    if args.leader_trace:
        from ur12e_collection.simulation.leader import Trace

        trace = Trace(args.leader_trace, speed=args.leader_speed)
    output = pathlib.Path("/results") / f"session-{time.time_ns()}"
    output.mkdir()
    report = {"status": "FAIL", "episodes": [], "simulated": True}
    owner = None
    (output / "report.json").write_text(json.dumps(report, indent=2))
    try:
        with connection.open_station() as station:
            owner = session.create(
                station,
                output,
                observe=args.ros_observe,
                inputs=session.Inputs(trace, camera_input),
            )
            try:
                for index in range(args.episodes):
                    press(owner)
                    wait(owner, "ready")
                    press(owner)
                    wait(owner, "recording")
                    started = owner.active.started_ns / 1e9
                    killed = False
                    while time.monotonic() - started < args.seconds:
                        tick(owner)
                        if (
                            args.kill_observer
                            and not killed
                            and time.monotonic() - started > args.seconds / 2
                        ):
                            owner.observer.process.kill()
                            killed = True
                    if args.kill_observer:
                        assert owner.observer.health()["state"] == "failed"
                        assert owner.observer.health()["dropped_records"] > 0
                    elif args.ros_observe:
                        assert owner.observer.health()["state"] == "online"
                    owner.key(" ", time.monotonic_ns())
                    wait(owner, "held")
                    completed = owner.completed[-1]
                    print(
                        json.dumps(
                            {
                                "episode": index,
                                "state": owner.state,
                                "matching": completed["matching"],
                            }
                        ),
                        flush=True,
                    )
                    seconds = (
                        completed["stop_receipt_ns"]
                        - completed["start_receipt_ns"]
                    ) / 1e9
                    counts = completed["recording"]["verification"]["counts"]
                    assert args.seconds <= seconds < args.seconds + 0.15
                    assert counts["camera/frame_set"] / seconds >= 28.5
                    assert counts["control/command"] / seconds >= (
                        0.9 * owner.snapshot["control"]["control_hz"]
                    )
                    report["episodes"].append(completed)
                    if args.seconds >= 40:
                        context = completed["recording"]["snapshot"]["control"]
                        rows = [
                            json.loads(message.data)
                            for _, message in mcap_read.messages(
                                owner.active.destination / "episode.mcap",
                                (
                                    "camera/frame_set",
                                    "diagnostics/frame_rejection",
                                ),
                            )
                        ]
                        completed["quality"] = decisions(
                            rows,
                            completed["start_receipt_ns"],
                            completed["stop_receipt_ns"],
                            context.get("inputs", {}).get("cameras"),
                        )
                    (output / "report.json").write_text(
                        json.dumps(report, indent=2)
                    )

                press(owner, "a")
                assert (
                    json.loads(
                        (owner.active.destination / "outcome.json").read_text()
                    )["disposition"]
                    == "discarded"
                )
                report["held_discard"] = True
            finally:
                owner.close()
        for completed in report["episodes"]:
            storage.verify_episode(output / completed["episode"])
        report["status"] = "PASS"
    except BaseException as error:
        report["status"] = "FAIL"
        report["error"] = str(error)
        if owner is not None:
            report["timings"] = owner.timings
        report["traceback"] = traceback.format_exc()
    finally:
        if owner is not None:
            report["timings"] = owner.timings
            if owner.observer is not None:
                report["observer"] = owner.observer.health()
        (output / "report.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "report": str(output / "report.json"),
                "status": report["status"],
                "error": report.get("error"),
            }
        )
    )
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
