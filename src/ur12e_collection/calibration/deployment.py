"""Portable calibration locations and a device-free motion preview."""

import json
import math
import time

from ur12e_collection.calibration import manifest
from ur12e_collection.control import model
from ur12e_collection.followers.config import resolve


def configure(args):
    """Fill only missing paths; explicit CLI paths always take precedence."""
    location = args.calibration_config
    if location is None:
        return
    location = location.expanduser().resolve()
    value = json.loads(location.read_text(encoding="utf-8"))
    manifest.keys(value, ("schema_version", "output_root", "routes"))
    if value["schema_version"] != 1:
        raise ValueError("unsupported calibration deployment version")
    manifest.keys(value["routes"], (), ("wrist", "third_left", "third_right"))
    root = resolve(location.parent, value["output_root"]) / args.role
    if args.poses is None and not (args.solve or args.verify or args.activate):
        args.poses = resolve(location.parent, value["routes"][args.role])
    if args.output is None and not (args.verify or args.activate):
        group = "results" if args.solve else "runs"
        args.output = root / group / str(time.time_ns())
    if args.result_output is None and not (args.verify or args.activate):
        args.result_output = root / "results" / args.output.name


def preview(route, limits):
    """Describe joint interpolation, not Cartesian clearance or real timing."""
    previous = route.start
    segments = []
    speed, acceleration = limits.ready_speed, limits.ready_acceleration
    for pose in route.poses:
        for index, target in enumerate(pose.waypoints):
            delta = [math.degrees(b - a) for a, b in zip(previous, target)]
            distance = model.distance(previous, target)
            duration = (
                2 * math.sqrt(distance / acceleration)
                if distance <= speed * speed / acceleration
                else distance / speed + speed / acceleration
            )
            segments.append(
                {
                    "pose_id": pose.pose_id,
                    "segment": index + 1,
                    "delta_deg": [round(v, 3) for v in delta],
                    "nominal_motion_s": round(duration, 2),
                    "capture": index == len(pose.waypoints) - 1,
                    "split": pose.split,
                }
            )
            previous = target
    return {
        "state": "valid_structure",
        "motion_ready": False,
        "role": route.role,
        "checkpoints": len(route.poses),
        "start_deg": [round(math.degrees(v), 3) for v in route.start],
        "end_deg": [round(math.degrees(v), 3) for v in previous],
        "speed_deg_s": math.degrees(speed),
        "acceleration_deg_s2": math.degrees(acceleration),
        "stationary_capture_s": 2,
        "nominal_total_s": round(
            sum(s["nominal_motion_s"] for s in segments) + 2 * len(route.poses),
            2,
        ),
        "path_clearance_verified": False,
        "segments": segments,
    }
