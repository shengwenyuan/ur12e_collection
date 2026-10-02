"""Verified AprilGrid bundles adapted explicitly to station snapshots."""

import dataclasses
import hashlib

from ur12e_collection import station
from ur12e_collection.calibration import manifest, pipeline, routes


def snapshot(value, bundle):
    """Keep fitted optics, frame directions and evidence in schema 3."""
    route = value["route"]
    optics = value["intrinsics"]
    matrix = optics["matrix"]
    context = {
        key: route[key]
        for key in ("role", "camera_serial", "base_id", "mount_id")
    }
    context.update(
        simulated=value["simulated"],
        script_revision=manifest.digest(route),
        board={"type": "aprilgrid", **route["board"]},
        intrinsics={
            "width": 640,
            "height": 480,
            "fx": matrix[0][0],
            "fy": matrix[1][1],
            "ppx": matrix[0][2],
            "ppy": matrix[1][2],
            "model": optics["model"],
            "coeffs": optics["coeffs"],
        },
        thresholds=value["solution"]["thresholds"],
        detection_limits=dataclasses.asdict(routes.DETECTION),
    )
    result = {
        "schema_version": 3,
        "context": context,
        "solution": value["solution"],
        "detections": value["detections"],
        "evidence": value["evidence"]
        | {
            "result.json": hashlib.sha256(
                (bundle / "result.json").read_bytes()
            ).hexdigest(),
        },
    }
    result["calibration_id"] = manifest.digest(result)
    manifest.result(result)
    return result


def activate(bundle, station_path, role):
    """Recompute first; identity or geometry failure preserves the station."""
    value = pipeline.verify(bundle)
    if value["route"]["role"] != role:
        raise ValueError("selected camera differs from calibration result")
    converted = snapshot(value, bundle)

    def change(config):
        selected = config["calibration"] or {"schema_version": 1, "cameras": {}}
        selected["cameras"][role] = converted
        config["calibration"] = selected
        return config

    return station.update(station_path, change)
