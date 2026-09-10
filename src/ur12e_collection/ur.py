"""Bounded read-only UR diagnostics; no control or IO interface is imported."""

import json
import multiprocessing
import pathlib
import socket
import time
from typing import Any

from ur12e_collection import wire, workers

DASHBOARD_QUERIES = (
    "PolyscopeVersion",
    "get serial number",
    "get robot model",
    "robotmode",
    "safetystatus",
    "is in remote control",
)

OUTPUT_FIELDS = [
    "timestamp",
    "actual_q",
    "actual_qd",
    "actual_current",
    "actual_TCP_pose",
    "robot_mode",
    "safety_mode",
]


def dashboard(host: str) -> dict:
    """Read only the fixed query allowlist, with bounded socket operations."""
    result = {"responses": {}, "state": "failed"}
    try:
        with socket.create_connection((host, 29999), timeout=2) as connection:
            result["greeting"] = (
                wire.line(connection, time.monotonic_ns() + 2_000_000_000, 4096)
                .decode()
                .strip()
            )
            for query in DASHBOARD_QUERIES:
                connection.settimeout(2)
                connection.sendall((query + "\n").encode("ascii"))
                reply = wire.line(
                    connection, time.monotonic_ns() + 2_000_000_000, 4096
                )
                result["responses"][query] = reply.decode().strip()
        result["state"] = "available"
    except (OSError, UnicodeError, ValueError) as error:
        result["error"] = str(error)
    return result


def _sample(receiver: Any) -> dict:
    start = receiver.getTimestamp()
    result = {
        "controller_timestamp_start_s": start,
        "joint_positions_rad": receiver.getActualQ(),
        "joint_velocities_rad_s": receiver.getActualQd(),
        "joint_currents_a": receiver.getActualCurrent(),
        "tcp_pose_m_rotvec_rad": receiver.getActualTCPPose(),
        "robot_mode": receiver.getRobotMode(),
        "safety_mode": receiver.getSafetyMode(),
        "received_monotonic_ns": time.monotonic_ns(),
    }
    result["controller_timestamp_end_s"] = receiver.getTimestamp()
    return result


def _receive(host: str, seconds: float, pipe: Any) -> None:
    receiver = None
    result = {"state": "failed", "samples": []}
    try:
        import rtde_receive  # pylint: disable=import-outside-toplevel,import-error

        receiver = rtde_receive.RTDEReceiveInterface(host, 125.0)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result["samples"].append(_sample(receiver))
            time.sleep(1 / 30)
        result["state"] = "available"
    except (ImportError, OSError, RuntimeError) as error:
        result["error"] = str(error)
    finally:
        if receiver is not None:
            try:
                receiver.disconnect()
            except RuntimeError as error:
                result.update(state="failed", cleanup_error=str(error))
        pipe.send(result)
        pipe.close()


def receive(host: str, seconds: float) -> dict:
    """Isolate potentially blocking native SDK connection/read/cleanup calls."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_receive, args=(host, seconds, child), daemon=True
    )
    process.start()
    child.close()
    try:
        if parent.poll(seconds + 8):
            try:
                return parent.recv()
            except EOFError:
                return {
                    "state": "failed",
                    "error": "RTDE worker exited without a report",
                }
        return {"state": "failed", "error": "RTDE worker timed out"}
    finally:
        workers.stop(process)
        parent.close()


def probe(host: str, seconds: float, output: pathlib.Path) -> dict:
    """Save actual Dashboard and RTDE responses; never request robot motion."""
    if not host or not 0 < seconds <= 10:
        raise ValueError("a host and 0 < seconds <= 10 are required")
    if output.exists():
        raise FileExistsError(output)
    report = {
        "schema_version": 1,
        "host": host,
        "read_only": True,
        "dashboard": dashboard(host),
        "rtde": receive(host, seconds),
        "sampling_note": (
            "125 Hz receive, ~30 Hz diagnostic reads; " "not a servo rate"
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def coherent_sample(receiver: Any) -> dict:
    """Reject getter reads spanning timestamp changes; not a servo interface."""
    for _ in range(5):
        result = _sample(receiver)
        if (
            result["controller_timestamp_start_s"]
            == result["controller_timestamp_end_s"]
        ):
            return result
    raise RuntimeError("UR feedback changed during every timestamp bracket")
