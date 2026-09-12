"""Physical readiness is read-only until explicit operator execution."""

import dataclasses
import math
import time

from ur12e_collection import hande, ur
from ur12e_collection.control import model, settling
from ur12e_collection.control.ur import read_state
from ur12e_collection.physical import network


def identity(config, executing):
    """Use the existing Dashboard allowlist, with no mode/program writes."""
    follower = config["follower"]
    route = network.route(follower["host"], follower["interface"])
    report = ur.dashboard(follower["host"])
    values = report["responses"]
    if (
        report["state"] != "available"
        or values.get("get serial number") != follower["serial"]
    ):
        raise model.ControlError("robot identity unavailable or mismatched")
    if (
        values.get("robotmode") != "Robotmode: RUNNING"
        or values.get("safetystatus") != "Safetystatus: NORMAL"
    ):
        raise model.ControlError("robot must be powered with normal safety")
    if executing and values.get("is in remote control") != "true":
        raise model.ControlError("operator must select Remote Control")
    return {"route": route, "dashboard": report}


def receiver(host):
    """Load output-only SDK; no control import is reachable from preflight."""
    import rtde_receive  # pylint: disable=import-outside-toplevel,import-error

    return rtde_receive.RTDEReceiveInterface(
        host, 125.0, ur.OUTPUT_FIELDS + ["runtime_state"]
    )


def stationary(rx, limits):
    """Require an idle program and advancing stationary feedback in bounds."""
    stable = settling.Standstill(limits.freshness_ns)
    deadline = time.monotonic() + 2
    previous = None
    while time.monotonic() < deadline:
        state = read_state(rx)
        limits.check(state.q)
        if not state.holding_allowed:
            raise model.ControlError(
                "robot program must be stopped before ownership"
            )
        if max(map(abs, state.qd)) > limits.stopped_speed:
            raise model.ControlError("robot is moving before ownership")
        if previous is not None and state.timestamp < previous:
            raise model.ControlError("controller restarted during preflight")
        previous = state.timestamp
        if stable.update(state.qd, state.timestamp, time.monotonic_ns()):
            return state
        time.sleep(0.008)
    raise model.ControlError(
        "stationary progressing robot feedback unavailable"
    )


def check(config):
    """Check readiness without opening USB or writing devices."""
    report = identity(config, False)
    rx = receiver(config["follower"]["host"])
    try:
        report["robot"] = dataclasses.asdict(stationary(rx, config["limits"]))
    finally:
        rx.disconnect()
    reader = hande.Reader(config["follower"]["host"], config["gripper"]["port"])
    try:
        registers, stamp = reader.read()
        values = dict(registers)
        report["gripper"] = {"registers": values, "acquired_ns": stamp}
        if values["STA"] != 3 or values["FLT"]:
            raise model.ControlError("Hand-E inactive or faulted")
        report["gripper_open"] = (
            values["POS"] <= config["gripper"]["open_tolerance"]
            and values["OBJ"] != 0
        )
    finally:
        reader.close()
    return report | {"read_only": True}


def handover(read, before, limits, emit):
    """Observe SDK startup with bounded waiting and distinct failure reasons."""
    started = time.monotonic_ns()
    progressing, previous = started, before.timestamp
    waiting = False
    emit("handover_before", feedback=before)
    while True:
        after = read()
        now = time.monotonic_ns()
        delta = model.distance(before.q, after.q)
        speed = max(map(abs, after.qd))
        modes = (after.robot_mode, after.safety_mode, after.runtime_state)
        if after.timestamp > previous:
            progressing = now
        failures = []
        if modes[:2] != (7, 1) or modes[2] not in (0, 1, 2):
            failures.append("unexpected controller modes")
        if delta > limits.arrival:
            failures.append("joint displacement exceeded handover limit")
        if speed > limits.stopped_speed:
            failures.append("joint speed exceeded handover limit")
        if after.timestamp < previous:
            failures.append("controller timestamp regressed")
        if (
            not 0 <= now - after.received_ns <= limits.freshness_ns
            or now - progressing > limits.freshness_ns
        ):
            failures.append("handover feedback stale")
        if now - started >= 1_000_000_000 and not after.motion_allowed:
            failures.append("controller startup timed out")
        detail = (
            f"modes={modes}, delta={math.degrees(delta):.5f} deg, "
            f"speed={math.degrees(speed):.5f} deg/s"
        )
        emit(
            "handover_feedback",
            feedback=after,
            outcome=(
                "rejected"
                if failures
                else (
                    "accepted"
                    if after.motion_allowed
                    and after.timestamp > before.timestamp
                    else "waiting"
                )
            ),
            reasons=failures,
            delta_rad=delta,
            speed_rad_s=speed,
        )
        if failures:
            raise model.ControlError(
                f"handover rejected: {'; '.join(failures)}; {detail}"
            )
        if after.motion_allowed and after.timestamp > before.timestamp:
            print(f"Handover accepted: {detail}", flush=True)
            return after
        if not waiting:
            print(f"Waiting for controller startup: {detail}", flush=True)
            waiting = True
        previous = after.timestamp
        time.sleep(0.008)
