"""Test the saved native Home node; no SDK motion program runs concurrently."""

import json
import pathlib
import time

import rtde_receive

from ur12e_collection.control.backends import open_backend
from ur12e_collection.control.model import distance
from ur12e_collection.control.owner import Controller
from ur12e_collection.simulation import connection, profile


def offset():
    with open_backend("ursim") as transport:
        control = Controller(transport, profile.LIMITS)
        state = control.tick(time.monotonic_ns())
        target = (0.8, *profile.HOME[1:])
        control.route((target,), state.q, time.monotonic_ns())
        while control.state != "hold":
            control.tick(time.monotonic_ns())
            time.sleep(0.02)
        control.close()


def trial(interrupt):
    offset()
    lease = connection.Lease(pathlib.Path("/sim-lock/controller.lock"))
    address = connection.verify_boundary()
    receiver = rtde_receive.RTDEReceiveInterface(
        address, 125.0, ["actual_q", "actual_qd", "runtime_state"]
    )
    rows = []
    try:
        assert (
            connection.dashboard(address, "get serial number") == profile.SERIAL
        )
        assert connection.dashboard(
            address, "load /ursim/programs/ready.urp"
        ).startswith("Loading program:")
        assert connection.dashboard(address, "play") == "Starting program"
        # Each Dashboard command opens and closes a connection. This deliberate
        # disconnect checks whether native Home requires a separate watchdog.
        start = time.monotonic()
        stop_request = None
        was_moving = False
        while time.monotonic() - start < 12.0:
            elapsed = time.monotonic() - start
            q = tuple(receiver.getActualQ())
            speed = max(map(abs, receiver.getActualQd()))
            runtime = receiver.getRuntimeState()
            rows.append(
                {"seconds": elapsed, "q": q, "speed": speed, "runtime": runtime}
            )
            was_moving |= speed > 0.05
            if (
                interrupt
                and was_moving
                and elapsed >= 0.8
                and stop_request is None
            ):
                assert connection.dashboard(address, "stop") == "Stopped"
                stop_request = elapsed
            if was_moving and runtime == 1 and speed < 0.01:
                break
            time.sleep(0.01)
        assert was_moving and runtime == 1 and speed < 0.01
        peak = max(r["speed"] for r in rows)
        assert peak < 0.28, peak
        error = distance(q, profile.HOME)
        if interrupt:
            assert elapsed - stop_request < 1.0
            assert error > 0.05, "stop incorrectly returned HOME"
        else:
            assert error < 0.01, error
        anchor = q
        until = time.monotonic() + 1.0
        drift = 0.0
        while time.monotonic() < until:
            drift = max(drift, distance(anchor, tuple(receiver.getActualQ())))
            assert max(map(abs, receiver.getActualQd())) < 0.01
            time.sleep(0.01)
        assert drift < 0.01
        return {
            "interrupted": interrupt,
            "peak_speed_rad_s": peak,
            "home_error_rad": error,
            "stop_seconds": elapsed - stop_request if interrupt else None,
            "hold_drift_rad": drift,
            "samples": rows,
        }
    finally:
        connection.dashboard(address, "stop")
        receiver.disconnect()
        lease.close()


def run():
    report = {"status": "FAIL", "trials": []}
    try:
        for interrupt in (False, True, False):
            report["trials"].append(trial(interrupt))
        report["status"] = "PASS"
        report["disconnect_stops_program"] = False
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        path = pathlib.Path("/results") / f"native-home-{time.time_ns()}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        print(
            json.dumps(
                {
                    "report": str(path),
                    "status": report["status"],
                    "error": report.get("error"),
                }
            )
        )


if __name__ == "__main__":
    run()
