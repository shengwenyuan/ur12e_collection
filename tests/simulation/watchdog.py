"""Kill and stall the real SDK client; observe URSim from another process."""

import json
import multiprocessing
import os
import pathlib
import signal
import sys
import time

import rtde_receive

from ur12e_collection.control.backends import open_backend
from ur12e_collection.control.model import ControlError, distance
from ur12e_collection.control.owner import Controller
from ur12e_collection.simulation import connection, profile


def actor(pipe, move):
    try:
        with open_backend("ursim") as transport:
            control = Controller(transport, profile.LIMITS)
            feedback = control.tick(time.monotonic_ns())
            if move:
                goal = (feedback.q[0] + 1.5, *feedback.q[1:])
                control.route((goal,), feedback.q, time.monotonic_ns())
            pipe.send("connected")
            while True:
                control.tick(time.monotonic_ns())
                time.sleep(0.02)
    except Exception as error:
        pipe.send(str(error))


def trial(sig):
    address = connection.verify_boundary()
    receiver = rtde_receive.RTDEReceiveInterface(
        address, 125.0, ["actual_q", "actual_qd", "runtime_state"]
    )
    process = None
    rows = []
    try:
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        process = ctx.Process(target=actor, args=(child, True))
        process.start()
        assert parent.poll(15), "actor startup timeout"
        assert parent.recv() == "connected"
        # The second owner must fail at the lease, before even reading Dashboard.
        try:
            with open_backend("ursim"):
                raise AssertionError("second owner connected")
        except ControlError as error:
            assert "another controller" in str(error)
        until = time.monotonic() + 3.0
        while max(map(abs, receiver.getActualQd())) < 0.1:
            assert time.monotonic() < until, "actor never moved"
            time.sleep(0.01)
        started = time.monotonic()
        os.kill(process.pid, sig)
        stopped_at = None
        anchor = None
        max_drift = 0.0
        while time.monotonic() - started < 2.5:
            elapsed = time.monotonic() - started
            q = tuple(receiver.getActualQ())
            speed = max(map(abs, receiver.getActualQd()))
            runtime = receiver.getRuntimeState()
            rows.append(
                {"seconds": elapsed, "q": q, "speed": speed, "runtime": runtime}
            )
            if stopped_at is None and speed < 0.01 and runtime == 1:
                stopped_at, anchor = elapsed, q
            if stopped_at is not None:
                max_drift = max(max_drift, distance(anchor, q))
                assert speed < 0.01, "motion resumed"
            time.sleep(0.01)
        assert stopped_at is not None and stopped_at < 1.0, stopped_at
        assert max_drift < 0.01, max_drift
        if process.is_alive():
            process.kill()
        process.join(3)
        # The firmware may latch a protective stop after losing RTDE inputs.
        # A reconnect rejection is required until explicit operator recovery.
        restart_rejected = False
        try:
            with open_backend("ursim") as transport:
                control = Controller(transport, profile.LIMITS)
                until = time.monotonic() + 1.0
                while time.monotonic() < until:
                    feedback = control.tick(time.monotonic_ns())
                    assert distance(anchor, feedback.q) < 0.01
                    assert max(map(abs, feedback.qd)) < 0.01
                    time.sleep(0.02)
                control.close()
        except ControlError as error:
            assert "safety is not normal" in str(error)
            restart_rejected = True
        return {
            "signal": sig.name,
            "restart_rejected": restart_rejected,
            "stop_seconds": stopped_at,
            "hold_drift_rad": max_drift,
            "samples": rows,
        }
    finally:
        if process is not None:
            if process.is_alive():
                process.kill()
            process.join(3)
        receiver.disconnect()


def run():
    result = {"status": "FAIL", "trials": []}
    try:
        sig = signal.SIGSTOP if sys.argv[1:] == ["stall"] else signal.SIGKILL
        result["trials"].append(trial(sig))
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        path = pathlib.Path("/results") / f"watchdog-{time.time_ns()}.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        print(
            json.dumps(
                {
                    "report": str(path),
                    "status": result["status"],
                    "error": result.get("error"),
                }
            )
        )


if __name__ == "__main__":
    run()
