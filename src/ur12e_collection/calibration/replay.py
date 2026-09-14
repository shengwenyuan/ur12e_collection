"""Authorized physical calibration under the shared motion owner."""

import contextlib
import dataclasses
import fcntl
import os
import pathlib
import signal
import sys
import time

from ur12e_collection import filesystem, station
from ur12e_collection.calibration import camera, geometry, rollout, routes
from ur12e_collection.control import model, owner, trace
from ur12e_collection.followers import config as configuration
from ur12e_collection.physical import transport as hardware


def prepare(args):
    """Validate all files/identities before any camera or robot connection."""
    config = configuration.load(args.config)
    if config["follower"]["backend"] != "ur":
        raise ValueError(
            "calibration launcher requires the physical UR profile"
        )
    route = routes.load(args.poses, args.role, config["limits"])
    station_config = station.load(args.station)
    observed = station_config["cameras"][route.role]
    if (
        observed["serial"] != route.document["camera_serial"]
        or observed["model"] != route.document["camera_model"]
        or config["follower"]["serial"] != route.document["robot_serial"]
    ):
        raise ValueError("calibration route differs from configured hardware")
    setup = station_config.get("setup")
    if setup and (
        setup["simulated"]
        or setup["base_id"] != route.document["base_id"]
        or setup["mounts"][route.role] != route.document["mount_id"]
    ):
        raise ValueError("calibration route differs from declared setup")
    return config, route


def _interrupt(_number, _frame):
    raise KeyboardInterrupt


def drive(capture, source, log):
    """Run the single controller at 120 Hz; OpenCV never runs on this thread."""
    controller = capture.traversal.controller
    controller.tick(time.monotonic_ns())
    capture.start(time.monotonic_ns())
    while capture.traversal.state != "complete":
        started = time.monotonic_ns()
        capture.traversal.step(started)
        log.emit(
            "feedback",
            state=controller.progress.feedback,
            checkpoint=capture.traversal.index,
        )
        frame = source.poll()
        if frame is not None and capture.traversal.state != "complete":
            capture.traversal.image(frame)
        time.sleep(
            max(0, 1 / model.COMMAND_HZ - (time.monotonic_ns() - started) / 1e9)
        )


# Resource order is explicit: stop the owner before camera/log/lease cleanup.
# pylint: disable=too-many-locals


def run(args):
    """Acquire, stop, persist and publish; failures retain partial evidence."""
    config, route = prepare(args)
    if args.validate_only:
        return {
            "state": "valid_structure",
            "motion_ready": False,
            "checkpoints": len(route.poses),
            "role": route.role,
        }
    if not args.operator_approved:
        raise ValueError("calibration replay requires --operator-approved")
    if sys.platform != "linux":
        raise ValueError("physical calibration runs on the Ubuntu station")
    lease_path, destination, partial = _paths(args.output)
    capture = None
    document = {
        "schema_version": 2,
        "state": "partial",
        "simulated": False,
        "route": route.document,
        "limits": dataclasses.asdict(config["limits"]),
        "image_id": os.environ.get("UR12E_IMAGE_ID", "unavailable"),
    }
    try:
        with contextlib.ExitStack() as stack:
            lease = stack.enter_context(
                pathlib.Path(lease_path).open("a", encoding="utf-8")
            )
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            log = trace.Trace(partial / "control")
            stack.callback(log.close)
            previous = signal.signal(signal.SIGTERM, _interrupt)
            stack.callback(signal.signal, signal.SIGTERM, previous)
            source = camera.Source(route)
            stack.callback(source.close)
            document["camera"] = source.ready()
            device = hardware.open_transport(config, emit=log.emit)
            controller = owner.Controller(device, config["limits"])
            stack.callback(controller.close)
            offset = device.control.getTCPOffset()
            geometry.pose(offset)
            document["tcp_offset"] = {
                "pose": list(offset),
                "source": "RTDEControlInterface.getTCPOffset",
                "received_monotonic_ns": time.monotonic_ns(),
            }
            capture = rollout.Capture(controller, route, offset)
            device.enable_watchdog()
            try:
                drive(capture, source, log)
                ending = device.control.getTCPOffset()
                changed = geometry.error(
                    geometry.pose(offset), geometry.pose(ending)
                )
                if max(changed.values()) > 1e-9:
                    raise ValueError(
                        "active TCP offset changed during calibration"
                    )
                document["tcp_offset_after"] = list(ending)
                document["observations"] = capture.document()
            except BaseException:
                controller.fail("calibration interrupted or failed")
                log.emit("calibration_aborted")
                raise
        document["state"] = "complete"
    finally:
        _save(partial, route, capture, document)
    filesystem.publish(partial, destination)
    return {
        "state": "complete",
        "run": str(destination),
        "observations": len(route.poses),
    }


def _save(partial, route, capture, document):
    """Persist selected images only after the owner has stopped."""
    if capture:
        images = partial / "images"
        images.mkdir()
        for index, pose in enumerate(route.poses):
            if pose.pose_id in capture.selected:
                frame, _ = capture.selected[pose.pose_id]
                (images / f"{index:03d}.png").write_bytes(frame.png)
        if document["state"] != "complete":
            document["partial_observations"] = [
                record for _, record in capture.selected.values()
            ]
    filesystem.write_json(partial / "run.json", document)


def _paths(output):
    """Reserve a fresh run while retaining the shared host lease inode."""
    lease_path = os.environ.get("UR12E_LEASE")
    if not lease_path:
        raise ValueError(
            "use the host launcher for exclusive physical ownership"
        )
    destination = output.expanduser().resolve()
    if destination.name.endswith((".partial", ".lock")):
        raise ValueError("reserved calibration output suffix")
    if destination.exists():
        raise FileExistsError(destination)
    partial = destination.with_name(destination.name + ".partial")
    partial.mkdir(parents=True)
    return lease_path, destination, partial
