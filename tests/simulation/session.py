"""Actual URSim control with persistent synthetic RGB-D recording acceptance."""

import argparse
import json
import pathlib
import time
import traceback

from ur12e_collection import storage
from ur12e_collection.simulation import connection, session


def tick(owner):
    started = time.monotonic()
    owner.step()
    time.sleep(max(0.0, 0.02 - (time.monotonic() - started)))


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
    args = parser.parse_args()
    output = pathlib.Path("/results") / f"session-{time.time_ns()}"
    output.mkdir()
    report = {"status": "FAIL", "episodes": [], "simulated": True}
    owner = None
    (output / "report.json").write_text(json.dumps(report, indent=2))
    try:
        with connection.open_station() as station:
            owner = session.create(station, output)
            try:
                for index in range(args.episodes):
                    press(owner)
                    wait(owner, "ready")
                    press(owner)
                    wait(owner, "recording")
                    started = owner.active.started_ns / 1e9
                    while time.monotonic() - started < args.seconds:
                        tick(owner)
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
                    assert counts["control/command"] / seconds >= 45
                    report["episodes"].append(completed)
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
