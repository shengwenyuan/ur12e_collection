"""Resource ownership and explicit device selection for native teleoperation."""

import contextlib
import fcntl
import json
import os
import pathlib
import signal
import sys
import time

from ur12e_collection.control import collection, console, model, trace
from ur12e_collection.followers import config as configuration
from ur12e_collection.followers import dispatch
from ur12e_collection.leader import mapping, native
from ur12e_collection.physical import preflight, transport as hardware
from ur12e_collection.physical import recording as physical_recording


# Resource order is intentionally visible in one lifecycle scope.
# pylint: disable=too-many-locals,too-many-arguments
def launch(
    path,
    stream,
    session_type,
    drive,
    *,
    operator_approved=False,
    preflight_only=False,
    recording_options=None,
):
    """Share input/lifecycle across explicitly configured follower adapters."""
    if sys.platform != "linux":
        raise ValueError("native teleoperation runs on the Ubuntu station")
    config = configuration.load(path)
    physical = config["follower"]["backend"] == "ur"
    if _preflight(config, recording_options, operator_approved, preflight_only):
        return 0
    calibration = mapping.load(config["leader"]["calibration"])
    with contextlib.ExitStack() as stack:
        log = None
        if physical:
            config["evidence"].mkdir(parents=True, exist_ok=True)
            lease_path = os.environ.get("UR12E_LEASE")
            if not lease_path:
                raise model.ControlError(
                    "use the host launcher for physical ownership"
                )
            lease = stack.enter_context(
                pathlib.Path(lease_path).open("a", encoding="utf-8")
            )
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            log = trace.Trace(config["evidence"] / str(time.time_ns()))
            stack.callback(log.close)
            log.emit(
                "configuration",
                config_path=str(path),
                calibration=calibration.document(),
                limits=config["limits"],
                guards=config["guards"],
                image_id=os.environ.get("UR12E_IMAGE_ID"),
                gripper=config["gripper"],
            )
            print(f"Evidence: {log.path}", flush=True)
        with console.keyboard(stream) as read_keys:
            capture = None
            if recording_options:
                capture = physical_recording.Resources(
                    config,
                    recording_options,
                    os.environ.get("UR12E_IMAGE_ID", "unavailable"),
                )
                stack.callback(capture.close)
                capture.start()
            leader = native.Leader(
                config["leader"]["device"], config["leader"]["baudrate"]
            )
            stack.callback(leader.close)
            # Physical preflight/SDK connection takes time. Start serial only
            # after it completes so its bounded queue cannot fill during setup.
            device = (
                dispatch.Group(hardware.open_transport(config, emit=log.emit))
                if physical
                else dispatch.open_group(config)
            )
            stack.callback(device.close)
            if capture:
                capture.readers.start(capture.recorder.poll)
            leader.start()
            if physical:
                device.primary.enable_watchdog()
            session = session_type(
                device,
                leader,
                calibration,
                config["limits"],
                config["gripper"]["closing_sign"],
                guards=config.get("guards"),
                home_open_gripper=config.get("home_open_gripper", True),
            )
            if capture:
                session = collection.Session(
                    session,
                    capture.recorder,
                    capture.readers,
                    capture.snapshot,
                    capture.output,
                )
            # The session owns cleanup before the lower-level resources close.
            stack.callback(session.close)
            previous = signal.signal(signal.SIGTERM, _interrupt)
            stack.callback(signal.signal, signal.SIGTERM, previous)
            try:
                return drive(session, read_keys, log)
            except (KeyboardInterrupt, EOFError):
                if log:
                    log.emit("interrupted")
                return 130
            except Exception as error:
                if log:
                    log.emit("fault", reason=str(error))
                raise


def _interrupt(_number, _frame):
    raise KeyboardInterrupt


def authorize(config, operator_approved):
    """Require explicit launch authorization before any control connection."""
    if not operator_approved:
        raise model.ControlError("physical launch requires --operator-approved")
    if config["follower"].get("servo_stop_deceleration_m_s2") is None:
        raise model.ControlError(
            "servo stop parameter needs operator alignment"
        )


def _preflight(config, recording_options, operator_approved, preflight_only):
    physical = config["follower"]["backend"] == "ur"
    if recording_options and (not physical or preflight_only):
        raise ValueError(
            "recording requires an explicit physical control session"
        )
    if physical:
        if preflight_only:
            print(json.dumps(preflight.check(config), indent=2))
            return True
        authorize(config, operator_approved)
    elif preflight_only:
        raise ValueError("preflight is a physical read-only operation")
    return False
