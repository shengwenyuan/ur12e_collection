"""Exercise active discard, recorder loss and Ctrl+C against actual URSim."""

import json
import os
import pathlib
import signal
import time
import traceback
from multiprocessing import shared_memory

from ur12e_collection.control.model import distance
from ur12e_collection.simulation import connection, session
from session import press, wait


def start(owner):
    press(owner)
    wait(owner, "ready")
    press(owner)
    wait(owner, "recording")
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        owner.step()
        time.sleep(0.02)


def held(station):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        state = station.read()
        if max(map(abs, state.qd)) < 0.01 and state.runtime_state == 1:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("fault did not stop the arm")
    anchor = state.q
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        assert distance(station.read().q, anchor) < 0.01
        time.sleep(0.02)
    return anchor


def main():
    output = pathlib.Path("/results") / f"session-faults-{time.time_ns()}"
    output.mkdir()
    report = {"status": "FAIL", "cases": []}
    try:
        with connection.open_station() as station:
            for kind in ("active_discard", "recorder_loss", "ctrl_c"):
                destination = output / kind
                destination.mkdir()
                owner = session.create(station, destination)
                slots = [v.memory.name for v in owner.recorder.slots.values()]
                try:
                    start(owner)
                    if kind == "active_discard":
                        owner.key("a", time.monotonic_ns())
                        wait(owner, "held")
                        outcome = json.loads(
                            (
                                owner.active.destination / "outcome.json"
                            ).read_text()
                        )
                        assert outcome["disposition"] == "discarded"
                        assert outcome["task_success"] is None
                    elif kind == "recorder_loss":
                        owner.recorder.process.kill()
                        owner.recorder.process.join(timeout=1)
                        try:
                            owner.step()
                        except RuntimeError:
                            pass
                        else:
                            raise AssertionError("recorder loss was ignored")
                        assert owner.state == "fault"
                    else:
                        try:
                            os.kill(os.getpid(), signal.SIGINT)
                        except KeyboardInterrupt:
                            owner.close()
                        else:
                            raise AssertionError("SIGINT was not delivered")
                finally:
                    owner.close()
                for name in slots:
                    try:
                        leaked = shared_memory.SharedMemory(name=name)
                    except FileNotFoundError:
                        continue
                    leaked.close()
                    raise AssertionError("recorder leaked shared camera slots")
                position = held(station)
                assert (
                    distance(
                        position,
                        (
                            0,
                            -1.5707963268,
                            -1.5707963268,
                            -1.5707963268,
                            1.5707963268,
                            0,
                        ),
                    )
                    > 0.03
                )
                if kind != "active_discard":
                    assert not (destination / "episode-0000").exists()
                    assert list(destination.glob("*.partial"))
                report["cases"].append(
                    {"case": kind, "status": "PASS", "timings": owner.timings}
                )
                print(json.dumps(report["cases"][-1]), flush=True)
        report["status"] = "PASS"
    except BaseException as error:
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
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
