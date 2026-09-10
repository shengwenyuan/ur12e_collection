"""Read-only ROS projections preserve M10 provenance and physical units."""

import dataclasses
import json
import math

from ur12e_collection import contracts


def quaternion(rotation: tuple) -> dict:
    """Convert a rotation vector to x/y/z/w without Euler-angle conventions."""
    if len(rotation) != 3 or not all(math.isfinite(v) for v in rotation):
        raise ValueError("rotation vector must have three finite values")
    angle = math.hypot(*rotation)
    if not math.isfinite(angle):
        raise ValueError("rotation magnitude is not finite")
    scale = math.sin(angle / 2) / angle if angle else 0.5
    return dict(
        zip(
            ("x", "y", "z", "w"),
            (*[v * scale for v in rotation], math.cos(angle / 2)),
        )
    )


def project(record, context: dict) -> dict:
    """Project recorded-window samples; outside-window status stays separate."""
    result = {
        "records": {
            "data": json.dumps(dataclasses.asdict(record), allow_nan=False)
        }
    }
    joint_topic = {
        "leader_intent": "leader_joints",
        "sent_command": "sent_joints",
        "ur_feedback": "actual_joints",
    }.get(record.kind)
    if joint_topic is None:
        return result
    stamp = (
        record.provenance.time.received_monotonic_ns
        + context["monotonic_to_unix_ns"]
    )
    if not 0 <= stamp < 2**31 * 1_000_000_000:
        raise ValueError("mapped receipt exceeds the ROS Time range")
    seconds, nanos = divmod(stamp, 1_000_000_000)
    header = {
        "stamp": {"sec": seconds, "nanosec": nanos},
        "frame_id": "ur/" + context["arm_id"] + "/base",
    }
    result[joint_topic] = {
        "header": header,
        "name": list(contracts.JOINT_NAMES),
        "position": list(map(float, record.joint_positions_rad)),
        "velocity": (
            list(map(float, record.joint_velocities_rad_s))
            if record.kind == "ur_feedback"
            else []
        ),
        # Motor currents are amperes, not joint effort/torque.
        "effort": [],
    }
    if record.kind == "ur_feedback":
        pose = record.tcp_pose_m_rotvec_rad
        result["tcp"] = {
            "header": header,
            "pose": {
                "position": dict(zip(("x", "y", "z"), map(float, pose[:3]))),
                "orientation": quaternion(pose[3:]),
            },
        }
    return result
