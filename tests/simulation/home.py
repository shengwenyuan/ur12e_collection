"""Native default HOME, exclusive SDK handover and client-loss acceptance."""

import json
import multiprocessing
import os
import pathlib
import time

import rtde_receive

from ur12e_collection import ur
from ur12e_collection.control.model import ControlError, distance
from ur12e_collection.control.owner import Controller
from ur12e_collection.control.ur import read_state
from ur12e_collection.simulation import connection, profile


def offset(station):
    with station.motion() as transport:
        owner = Controller(transport, profile.LIMITS)
        current = owner.tick(time.monotonic_ns())
        owner.route(
            ((3.0, -1.2, -1.9, -1.0, 1.2, 1.0),), current.q, time.monotonic_ns()
        )
        while owner.state != "hold":
            owner.tick(time.monotonic_ns())
            time.sleep(0.02)
        owner.close()


def ordinary(station, interrupt):
    offset(station)
    peak, rows = 0.0, []
    with station.home() as home:
        home.start()
        try:
            with station.motion():
                raise AssertionError("SDK acquired native ownership")
        except ControlError as error:
            assert "already owns" in str(error)
        started = time.monotonic()
        requested = None
        while home.state != "hold":
            feedback = home.step()
            speed = max(map(abs, feedback.qd))
            peak = max(peak, speed)
            rows.append(
                {
                    "elapsed": time.monotonic() - started,
                    "q": feedback.q,
                    "speed": speed,
                }
            )
            if (
                interrupt
                and requested is None
                and time.monotonic() - started > 0.7
            ):
                requested = time.monotonic()
                home.stop()
            time.sleep(0.01)
        stopped_in = time.monotonic() - requested if requested else None
        if interrupt:
            assert stopped_in < 1.0, stopped_in
            assert distance(feedback.q, profile.HOME) > 0.05
        else:
            assert distance(feedback.q, profile.HOME) < 0.01
            assert 1.0 < peak < 1.07, peak
        anchor = feedback.q
        until = time.monotonic() + 1.0
        while time.monotonic() < until:
            assert distance(home.step().q, anchor) < 0.01
            time.sleep(0.02)
    # Reacquisition is explicit and must start idle at the attained position.
    with station.motion() as transport:
        owner = Controller(transport, profile.LIMITS)
        until = time.monotonic() + 0.5
        while time.monotonic() < until:
            feedback = owner.tick(time.monotonic_ns())
            assert distance(anchor, feedback.q) < 0.01
            assert max(map(abs, feedback.qd)) < 0.01
            time.sleep(0.02)
        owner.close()
    return {
        "interrupted": interrupt,
        "peak_speed_rad_s": peak,
        "stop_seconds": stopped_in,
        "samples": rows,
    }


def leave_home_running(pipe):
    with connection.open_station() as station:
        with station.home() as home:
            home.start()
            pipe.send("started")
            os._exit(
                0
            )  # Deliberate client loss: no Python cleanup or heartbeat.


def client_loss():
    address = connection.verify_boundary()
    receiver = rtde_receive.RTDEReceiveInterface(
        address,
        125.0,
        ur.OUTPUT_FIELDS + ["runtime_state"],
    )
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=leave_home_running, args=(child,))
    try:
        process.start()
        assert parent.poll(10) and parent.recv() == "started"
        process.join(3)
        assert process.exitcode == 0
        started = time.monotonic()
        seen_motion = False
        rows = []
        while time.monotonic() - started < 8:
            state = read_state(receiver)
            seen_motion |= max(map(abs, state.qd)) > 0.1
            rows.append(
                {
                    "elapsed": time.monotonic() - started,
                    "q": state.q,
                    "runtime": state.runtime_state,
                }
            )
            assert state.safety_mode == 1
            if seen_motion and state.runtime_state == 1:
                assert distance(state.q, profile.HOME) < 0.01
                return {
                    "client_lost": True,
                    "home_completed": True,
                    "samples": rows,
                }
            time.sleep(0.01)
        raise AssertionError("native HOME did not finish after client exit")
    finally:
        if process.is_alive():
            process.kill()
            process.join(3)
        receiver.disconnect()


def run():
    result = {"status": "FAIL", "trials": []}
    try:
        with connection.open_station() as station:
            for interrupt in (False, True):
                result["trials"].append(ordinary(station, interrupt))
            offset(station)
        result["trials"].append(client_loss())
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        path = pathlib.Path("/results") / f"home-defaults-{time.time_ns()}.json"
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
