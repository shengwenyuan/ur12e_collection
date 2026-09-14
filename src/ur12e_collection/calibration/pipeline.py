"""Two-stage AprilGrid solve from replay evidence, without station mutation."""

import dataclasses
import hashlib
import json
import pathlib
import shutil

import cv2
import numpy as np

from ur12e_collection import filesystem
from ur12e_collection.calibration import (
    aprilgrid,
    geometry,
    intrinsic,
    manifest,
    routes,
)
from ur12e_collection.calibration.results import image_path
from ur12e_collection.control import model


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def readback(item, limits, offset):
    """Derive flange from fresh, stationary actual TCP readback."""
    raw = item["actual"]
    values = {
        field.name: raw[field.name] for field in dataclasses.fields(model.State)
    }
    for key in ("q", "qd", "currents", "tcp"):
        if values[key] is not None:
            values[key] = tuple(values[key])
    state = model.State(**values)
    limits.check(state.q)
    if not state.motion_allowed or state.tcp is None:
        raise ValueError("normal actual TCP readback is required")
    receipt = item["color"]["time"]["received_monotonic_ns"]
    exposure = item["exposure_monotonic_ns"]
    dwell = item["dwell"]
    if (
        not 0 <= receipt - state.received_ns <= 50_000_000
        or not dwell["start_receipt_ns"]
        <= exposure
        <= receipt
        < dwell["stop_receipt_ns"]
        or not 0 <= receipt - exposure <= 250_000_000
        or dwell["stop_receipt_ns"] - dwell["start_receipt_ns"] != 2_000_000_000
        or max(map(abs, state.qd)) >= limits.stopped_speed
    ):
        raise ValueError(
            "image lacks fresh stationary in-dwell actual readback"
        )
    flange = geometry.pose(state.tcp) @ geometry.inverse(geometry.pose(offset))
    if not np.allclose(
        flange, geometry.transform(item["T_base_flange"]), atol=1e-9, rtol=0
    ):
        raise ValueError("stored flange differs from actual TCP and offset")
    return state


# The evidence boundary validates identities, clocks and geometry together.
# pylint: disable=too-many-locals


def evaluate(root: pathlib.Path) -> dict:
    """Redetect PNG pixels, fit only training views and validate every stop."""
    document = json.loads((root / "run.json").read_text(encoding="utf-8"))
    if document["schema_version"] != 2 or document["state"] != "complete":
        raise ValueError("a completed schema-2 replay run is required")
    if not isinstance(document["simulated"], bool):
        raise ValueError("explicit simulation provenance required")
    values = dict(document["limits"])
    for key in ("lower", "upper", "ready"):
        values[key] = tuple(values[key])
    limits = model.Limits(**values)
    route = routes.parse(document["route"], document["route"]["role"], limits)
    offset, camera = _context(document, route)
    observations = document["observations"]
    if len(observations) != len(route.poses):
        raise ValueError("missing or extra independent capture observations")
    detections = []
    evidence = {"run.json": _digest(root / "run.json")}
    evidence.update(_trace_evidence(root, document["simulated"]))
    previous = (0, -1, -1)
    for item, target in zip(observations, route.poses):
        if (item["pose_id"], item["split"]) != (target.pose_id, target.split):
            raise ValueError("observation identity/split differs from route")
        state = readback(item, limits, offset["pose"])
        color = item["color"]
        times = (state.timestamp, color["time"]["source_ns"], color["sequence"])
        if any(a <= b for a, b in zip(times, previous)):
            raise ValueError("capture clocks or frame sequence did not advance")
        previous = times
        if (
            color["source_id"] != camera["serial"]
            or color["simulated"] != document["simulated"]
        ):
            raise ValueError("image provenance differs from its camera/run")
        if model.distance(state.q, target.waypoints[-1]) >= limits.arrival:
            raise ValueError("actual capture did not reach its checkpoint")
        path = image_path(root, item["image"])
        if item["image"] in evidence:
            raise ValueError("one image cannot represent multiple checkpoints")
        evidence[item["image"]] = _digest(path)
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None or bgr.shape != (
            route.profile["height"],
            route.profile["width"],
            3,
        ):
            raise ValueError("PNG differs from the acquired RGB profile")
        detections.append(
            aprilgrid.detect(
                cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB),
                aprilgrid.Grid(**route.document["board"]),
                routes.DETECTION,
            )
        )
    value = intrinsic.solve(detections, observations, route.profile, route.role)
    value.update(
        schema_version=2,
        simulated=document["simulated"],
        route=route.document,
        evidence=evidence,
        opencv_version=cv2.__version__,
    )
    value["calibration_id"] = manifest.digest(value)
    return value


def solve(run: pathlib.Path, destination: pathlib.Path) -> dict:
    """Copy verified observations; failures never replace any active result."""
    if run.name.endswith(".partial") or destination.name.endswith(
        (".partial", ".lock")
    ):
        raise ValueError("partial/reserved calibration path")
    expected = evaluate(run)
    if destination.exists():
        raise FileExistsError(destination)
    partial = destination.with_name(destination.name + ".partial")
    partial.mkdir(parents=True)
    for name in expected["evidence"]:
        target = partial / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(run / name, target)
    observed = evaluate(partial)
    if observed != expected:
        raise ValueError("calibration evidence changed during copy")
    filesystem.write_json(partial / "result.json", observed)
    filesystem.publish(partial, destination)
    return observed


def verify(bundle: pathlib.Path) -> dict:
    """Recompute both stages; a digest alone cannot validate geometry."""
    if bundle.name.endswith(".partial"):
        raise ValueError("partial bundle cannot be verified")
    stored = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    if evaluate(bundle) != stored:
        raise ValueError("calibration result or evidence differs")
    return stored


def _context(document, route):
    """Require stable active TCP offset and observed camera identity."""
    offset = document["tcp_offset"]
    if offset["source"] != "RTDEControlInterface.getTCPOffset":
        raise ValueError("measured active TCP offset provenance required")
    if not np.allclose(
        geometry.pose(offset["pose"]),
        geometry.pose(document["tcp_offset_after"]),
        atol=1e-9,
        rtol=0,
    ):
        raise ValueError("active TCP offset changed")
    if not document["simulated"] and any(
        item["color"]["time"]["source_clock"] != "timestamp_domain.global_time"
        for item in document["observations"]
    ):
        raise ValueError("physical calibration requires camera global time")
    camera = document["camera"]
    if any(
        camera[k] != route.document[r]
        for k, r in (
            ("serial", "camera_serial"),
            ("model", "camera_model"),
            ("profile", "profile"),
        )
    ):
        raise ValueError("observed camera differs from route identity/profile")
    return offset, camera


def _trace_evidence(root, simulated):
    """Keep physical motion and stop evidence alongside the selected images."""
    evidence = {}
    trace = root / "control/trace.jsonl"
    if trace.is_file():
        evidence["control/trace.jsonl"] = _digest(trace)
    elif not simulated:
        raise ValueError("physical run requires a motion/stop trace")
    return evidence
