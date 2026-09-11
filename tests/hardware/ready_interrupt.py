"""Approved READY/SIGINT diagnostic, outside production entrypoints."""

import argparse
import fcntl
import hashlib
import json
import math
import multiprocessing
import os
import pathlib
import signal
import threading
import time

from ur12e_collection.control import settling
from ur12e_collection import ur
from ur12e_collection.control.ur import read_state

READY = [0, -90, -90, -90, 90, 0]
PARAMETERS = {
    "target_deg": READY,
    "speed_deg_s": 1,
    "acceleration_deg_s2": 2,
    "stop_deceleration_deg_s2": 2,
    "interrupt_after_s": 2,
    "observe_after_s": 30,
}


def event(kind, **values):
    """Timestamp actual dispatches separately from controller feedback."""
    return {
        "event": kind,
        "monotonic_ns": time.monotonic_ns(),
        "unix_ns": time.time_ns(),
        **values,
    }


def validate(plan):
    """Reject modified rates, expired reviews and unsafe numeric branches."""
    delay = plan.get("parameters", {}).get("interrupt_after_s")
    if (
        not isinstance(delay, int)
        or isinstance(delay, bool)
        or delay not in (2, 10)
    ):
        raise ValueError("interruption must be exactly 2 or 10 seconds")
    if json.dumps(plan.get("parameters"), sort_keys=True) != json.dumps(
        PARAMETERS | {"interrupt_after_s": delay}, sort_keys=True
    ):
        raise ValueError("test parameters differ from the reviewed protocol")
    if not 0 <= time.time_ns() - plan["created_unix_ns"] <= 600_000_000_000:
        raise ValueError("initial-pose review expired; prepare again")
    if not all(
        isinstance(plan.get(k), str) and plan[k] for k in ("host", "serial")
    ):
        raise ValueError("explicit host and serial required")
    q = plan["initial_deg"]
    if (
        not isinstance(q, list)
        or len(q) != 6
        or any(
            type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 360
            for v in q
        )
    ):
        raise ValueError("initial pose must contain six bounded finite angles")
    delta = max(abs(a - b) for a, b in zip(q, READY))
    minimum = max(4, delay * PARAMETERS["speed_deg_s"] + 0.5)
    if not minimum <= delta <= 180:
        raise ValueError(
            f"READY distance must be {minimum}..180 degrees without wrapping"
        )


def identity(plan, executing):
    """Only allowlisted Dashboard queries; never change robot state."""
    report = ur.dashboard(plan["host"])
    values = report["responses"]
    if (
        report["state"] != "available"
        or values.get("get serial number") != plan["serial"]
    ):
        raise ValueError("controller identity unavailable or mismatched")
    if values.get("safetystatus") != "Safetystatus: NORMAL":
        raise ValueError("normal safety required")
    if values.get("robotmode") != "Robotmode: RUNNING":
        raise ValueError("operator must power and enable the robot first")
    if executing and values.get("is in remote control") != "true":
        raise ValueError("operator must select Remote Control first")
    return report


def receiver(host):
    """Import only the output SDK; preparation never imports control."""
    import rtde_receive  # pylint: disable=import-outside-toplevel,import-error

    return rtde_receive.RTDEReceiveInterface(
        host, 125.0, ur.OUTPUT_FIELDS + ["runtime_state"]
    )


def stationary(rx, initial=None):
    """Require fresh feedback and standstill across 0.2 seconds."""
    stamps = []
    for _ in range(21):
        state = read_state(rx)
        if (state.robot_mode, state.safety_mode, state.runtime_state) != (
            7,
            1,
            1,
        ):
            raise ValueError(
                "normal stopped program required before SDK ownership"
            )
        if max(map(abs, state.qd)) > math.radians(0.01):
            raise ValueError("robot is moving; preparation cannot stop it")
        if (
            initial
            and max(abs(math.degrees(a) - b) for a, b in zip(state.q, initial))
            > 0.1
        ):
            raise ValueError("robot differs from reviewed initial pose")
        stamps.append(state.timestamp)
        time.sleep(0.01)
    if stamps[-1] <= stamps[0] or any(
        b < a for a, b in zip(stamps, stamps[1:])
    ):
        raise ValueError("controller feedback is stale or restarted")
    return state


def prepare(host, serial, output, environment="hardware", delay=2):
    """Save a read-only pose review; no control SDK or program upload."""
    plan = {"host": host, "serial": serial, "environment": environment}
    plan["identity"] = identity(plan, False)
    rx = receiver(host)
    try:
        state = stationary(rx)
        plan.update(
            created_unix_ns=time.time_ns(),
            initial_deg=list(map(math.degrees, state.q)),
            parameters=PARAMETERS | {"interrupt_after_s": delay},
        )
        validate(plan)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, indent=2)
        print(json.dumps(plan, indent=2))
    finally:
        rx.disconnect()


def drive(control, interrupted, emit, parameters=None):
    """One asynchronous READY request followed by explicit SIGINT stop."""
    if interrupted.is_set():
        raise RuntimeError("interrupted before motion; no target sent")
    if not control.setWatchdog(5.0) or not control.kickWatchdog():
        raise RuntimeError("controller watchdog setup failed")
    try:
        emit(event("move_request", parameters=parameters or PARAMETERS))
        if not control.moveJ(
            list(map(math.radians, READY)),
            math.radians(1),
            math.radians(2),
            True,
        ):
            raise RuntimeError("READY request rejected")
        emit(event("move_ack"))
        while not interrupted.wait(0.02):
            if not control.kickWatchdog():
                raise RuntimeError("watchdog update failed")
        emit(event("sigint_handled"))
    finally:
        emit(event("stop_request", deceleration_deg_s2=2))
        control.stopJ(math.radians(2), True)
        emit(event("stop_ack"))


def finish_stop(control, rx, emit):
    """Retain SDK ownership until fresh readback confirms settled standstill."""
    # Keep the watchdog fed during the explicitly requested deceleration.
    deadline = time.monotonic() + settling.STOP_TIMEOUT_NS / 1e9
    stable = settling.Standstill()
    previous = None
    advancing = time.monotonic()
    while time.monotonic() < deadline:
        if not control.kickWatchdog():
            raise RuntimeError("watchdog failed during stop")
        state = read_state(rx)
        if previous is None or state.timestamp > previous:
            advancing = time.monotonic()
        elif state.timestamp < previous:
            raise RuntimeError("feedback restarted during stop")
        previous = state.timestamp
        if time.monotonic() - advancing > 0.25:
            raise RuntimeError("feedback stale during stop")
        if stable.update(state.qd, state.timestamp, time.monotonic_ns()):
            emit(event("stop_script_request"))
            # The pinned binding returns None; the observer verifies runtime.
            control.stopScript()
            emit(event("owner_finished"))
            break
        time.sleep(0.02)
    else:
        raise RuntimeError(
            "standstill unconfirmed; operator intervention required"
        )


def motion(plan, channel):
    """Own control in a child; the independent observer outlives its SIGINT."""
    interrupted = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: interrupted.set())
    control = rx = None
    try:
        validate(plan)
        identity(plan, True)
        rx = receiver(plan["host"])
        stationary(rx, plan["initial_deg"])
        if interrupted.is_set():
            raise RuntimeError("interrupted before control connection")
        # Control creation uploads an idle SDK program: execute authorization
        # and preflight must already have passed before reaching this import.
        import rtde_control  # pylint: disable=import-outside-toplevel,import-error

        channel.send(event("control_connect"))
        control = rtde_control.RTDEControlInterface(
            plan["host"],
            50.0,
            rtde_control.RTDEControlInterface.FLAG_UPLOAD_SCRIPT
            | rtde_control.RTDEControlInterface.FLAG_UPPER_RANGE_REGISTERS,
        )
        try:
            state = read_state(rx)
            if (
                (state.robot_mode, state.safety_mode) != (7, 1)
                or max(map(abs, state.qd)) > math.radians(0.01)
                or max(
                    abs(math.degrees(a) - b)
                    for a, b in zip(state.q, plan["initial_deg"])
                )
                > 0.1
            ):
                raise RuntimeError("initial state changed during SDK setup")
            drive(control, interrupted, channel.send, plan["parameters"])
        finally:
            finish_stop(control, rx, channel.send)
    except Exception as error:  # pylint: disable=broad-exception-caught
        channel.send(event("owner_error", error=repr(error)))
    finally:
        if control is not None:
            control.disconnect()
        if rx is not None:
            rx.disconnect()
        channel.close()


class Observation:
    """One output reader with source-clock health and durable trace writes."""

    def __init__(self, rx, write):
        self.rx, self.write = rx, write
        self.previous = None
        self.advancing_at = time.monotonic()

    def sample(self, now):
        """Record a sample or fault; never reconnect or send control."""
        reason = None
        try:
            state = read_state(self.rx)
            if self.previous is None or state.timestamp > self.previous:
                self.advancing_at = now
            elif state.timestamp < self.previous:
                reason = "controller_timestamp_rollback"
            self.previous = state.timestamp
            if now - self.advancing_at > 0.25:
                reason = "stale_feedback"
            if (state.robot_mode, state.safety_mode) != (7, 1):
                reason = "abnormal_robot_state"
            if max(map(abs, state.qd)) > math.radians(1.2):
                reason = "observed_overspeed"
            self.write(
                event(
                    "feedback",
                    source_s=state.timestamp,
                    q=list(state.q),
                    qd=list(state.qd),
                    runtime=state.runtime_state,
                    safety=state.safety_mode,
                    robot=state.robot_mode,
                )
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            reason = "feedback_error"
            self.write(event(reason, error=repr(error)))
        if reason:
            self.write(event("observation_fault", reason=reason))
        return reason


def observe(rx, process, channel, stream, manual):
    """Observe independently and signal only the motion process."""

    def write(row):
        stream.write(json.dumps(row, allow_nan=False) + "\n")
        stream.flush()

    started = time.monotonic()
    requested = interrupted_at = None
    delay = None
    observation = Observation(rx, write)
    pipe_open = True
    while interrupted_at is None or time.monotonic() - interrupted_at < 30:
        while pipe_open and channel.poll():
            try:
                row = channel.recv()
            except EOFError:
                pipe_open = False
                break
            write(row)
            if row["event"] == "move_request":
                requested = row["monotonic_ns"] / 1e9
                delay = row["parameters"]["interrupt_after_s"]
        now = time.monotonic()
        reason = observation.sample(now)
        if manual.is_set():
            reason = reason or "operator_sigint"
        if interrupted_at is None:
            if requested is not None and now - requested >= delay:
                reason = reason or "scheduled_timer"
            if now - started > 15 and requested is None:
                reason = reason or "startup_timeout"
            if not process.is_alive():
                reason = reason or "owner_exited"
            if reason:
                write(event("sigint_sent", reason=reason, pid=process.pid))
                if process.is_alive():
                    os.kill(process.pid, signal.SIGINT)
                interrupted_at = now
        time.sleep(0.01)
    write(event("observation_complete"))


def execute(plan_path, output, approved):
    """Run only after operator approval; preparation cannot invoke this."""
    if not approved:
        raise ValueError("explicit operator launch approval required")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate(plan)
    identity(plan, True)
    output.mkdir(exist_ok=False)
    (output / "plan.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8"
    )
    lock_name = hashlib.sha256(plan["host"].encode()).hexdigest()[:16]
    with (output.parent / f"controller-{lock_name}.lock").open("a") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rx = receiver(plan["host"])
        process = None
        try:
            stationary(rx, plan["initial_deg"])
            context = multiprocessing.get_context("spawn")
            parent, child = context.Pipe(duplex=False)
            process = context.Process(
                target=motion, args=(plan, child), daemon=True
            )
            with (output / "trace.jsonl").open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(event("run_plan", plan=plan)) + "\n")
                stream.flush()
                process.start()
                child.close()
                print(
                    "Observer ready; timer starts on motion request",
                    flush=True,
                )
                manual = threading.Event()
                previous_handler = signal.signal(
                    signal.SIGINT, lambda *_: manual.set()
                )
                try:
                    observe(rx, process, parent, stream, manual)
                finally:
                    signal.signal(signal.SIGINT, previous_handler)
                    parent.close()
            process.join(2)
            if process.is_alive():
                raise RuntimeError(
                    "motion owner did not exit; review logs and robot"
                )
            if process.exitcode != 0:
                raise RuntimeError("motion owner exited abnormally")
        finally:
            if process is not None and process.is_alive():
                os.kill(process.pid, signal.SIGINT)
                process.join(3)
                if process.is_alive():
                    process.terminate()
                    process.join(2)
            rx.disconnect()


def main():
    """Keep read-only preparation distinct from explicit motion execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    draft = commands.add_parser("prepare")
    draft.add_argument("--host", required=True)
    draft.add_argument("--serial", required=True)
    draft.add_argument("--output", type=pathlib.Path, required=True)
    draft.add_argument(
        "--environment", choices=("hardware", "ursim"), default="hardware"
    )
    draft.add_argument(
        "--interrupt-after", type=int, choices=(2, 10), default=2
    )
    run = commands.add_parser("execute")
    run.add_argument("--plan", type=pathlib.Path, required=True)
    run.add_argument("--output", type=pathlib.Path, required=True)
    run.add_argument("--operator-approved", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(
            args.host,
            args.serial,
            args.output,
            args.environment,
            args.interrupt_after,
        )
    else:
        execute(args.plan, args.output, args.operator_approved)


if __name__ == "__main__":
    main()
