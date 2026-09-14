"""Known-camera evidence tests for the two-stage AprilGrid workflow."""

import copy
import dataclasses
import json

import cv2
import numpy as np
import pytest

from ur12e_collection import contracts, filesystem
from ur12e_collection.calibration import (
    aprilgrid,
    geometry,
    intrinsic,
    pipeline,
    routes,
)
from ur12e_collection.control import model
from ur12e_collection.simulation import profile

MODE = {"width": 1920, "height": 1080, "fps": 30, "format": "rgb8"}
K = np.array([[1450.0, 0, 960], [0, 1440.0, 540], [0, 0, 1]])


def route_document(role="third_left"):
    return {
        "schema_version": 1,
        "role": role,
        "camera_serial": "camera-test",
        "camera_model": "D405" if role == "wrist" else "D435IF",
        "robot_serial": "robot-test",
        "base_id": "base-test",
        "mount_id": "mount-test",
        "board_mount_id": "board-test",
        "board_attachment": "base" if role == "wrist" else "flange",
        "joint_names": routes.JOINT_NAMES,
        "units": "rad",
        "start_q": list(profile.HOME),
        "profile": (
            MODE.copy()
            if role != "wrist"
            else dict(MODE, width=1280, height=720)
        ),
        "board": {"tag_m": 0.028, "gap_m": 0.0084},
        "waypoints": [
            {
                "pose_id": f"p{i}",
                "q": [q + i * 0.001 for q in profile.HOME],
                "split": "training" if i < 15 else "validation",
            }
            for i in range(20)
        ],
    }


def projected(role="third_left"):
    rng = np.random.default_rng(12)
    camera = geometry.pose([0.07, -0.03, 0.11, 0.2, -0.1, 0.3])
    constant = geometry.pose([0.5, -0.2, 0.4, -0.1, 0.2, 0.4])
    objects = aprilgrid.Grid().points(np.arange(24))
    detections, observations = [], []
    for i in range(20):
        view = geometry.pose(
            np.r_[
                rng.uniform([-0.11, 0.04, 0.50], [-0.04, 0.12, 0.8]),
                rng.uniform([2.5, -0.6, -0.3], [2.8, 0.6, 0.3]),
            ]
        )
        robot = (
            constant @ geometry.inverse(view) @ geometry.inverse(camera)
            if role == "wrist"
            else camera @ view @ geometry.inverse(constant)
        )
        pixels = cv2.projectPoints(
            objects, cv2.Rodrigues(view[:3, :3])[0], view[:3, 3], K, None
        )[0].reshape(-1, 2)
        detections.append(
            {
                "object_points_m": objects.tolist(),
                "image_points": pixels.tolist(),
            }
        )
        observations.append(
            {
                "pose_id": f"p{i}",
                "split": "training" if i < 15 else "validation",
                "T_base_flange": robot.tolist(),
            }
        )
    return detections, observations, camera


def render(detection):
    gray = np.full((MODE["height"], MODE["width"]), 255, np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11
    )
    image_points = np.asarray(detection["image_points"], np.float32).reshape(
        24, 4, 2
    )
    source = np.array(
        [[-0.5, -0.5], [159.5, -0.5], [159.5, 159.5], [-0.5, 159.5]], np.float32
    )
    for tag, pixels in enumerate(image_points):
        marker = cv2.aruco.generateImageMarker(dictionary, tag, 160)
        h = cv2.getPerspectiveTransform(source, pixels)
        gray = np.minimum(
            gray,
            cv2.warpPerspective(
                marker, h, (MODE["width"], MODE["height"]), borderValue=255
            ),
        )
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


@pytest.mark.parametrize("role", ["third_left", "wrist"])
def test_no_prior_intrinsics_recovers_both_transform_directions(role):
    detections, observations, camera = projected(role)
    result = intrinsic.solve(detections, observations, MODE, role)
    key = "T_flange_camera" if role == "wrist" else "T_base_camera"
    assert np.allclose(result["intrinsics"]["matrix"], K, atol=0.03)
    assert (
        geometry.error(camera, result["solution"][key])["translation_m"] < 1e-5
    )
    assert not result["absolute_accuracy_verified"]
    assert not result["production_profile_compatible"]
    assert result["intrinsics"]["training_pose_ids"] == [
        f"p{i}" for i in range(15)
    ]


def test_held_out_error_cannot_be_fit_away():
    detections, observations, _ = projected()
    observations[-1]["T_base_flange"][0][3] += 0.01
    with pytest.raises(ValueError, match="validation"):
        intrinsic.solve(detections, observations, MODE, "third_left")


def test_real_apriltag_pixels_preserve_pdf_corner_orientation():
    detections, _, _ = projected()
    image = render(detections[0])
    found = aprilgrid.detect(image, aprilgrid.Grid(), routes.DETECTION)
    assert found["tag_ids"] == list(range(24))
    assert np.allclose(
        found["object_points_m"], detections[0]["object_points_m"]
    )
    assert (
        np.max(
            np.linalg.norm(
                np.array(found["image_points"]) - detections[0]["image_points"],
                axis=1,
            )
        )
        < 1
    )
    with pytest.raises(ValueError, match="blurred"):
        aprilgrid.detect(
            np.full_like(image, 255), aprilgrid.Grid(), routes.DETECTION
        )


@pytest.mark.parametrize(
    "change",
    [
        "count",
        "split",
        "duplicate",
        "units",
        "order",
        "bounds",
        "profile",
        "role",
    ],
)
def test_route_errors_fail_before_any_motion(change):
    doc = route_document()
    if change == "count":
        doc["waypoints"].pop()
    elif change == "split":
        doc["waypoints"][-1]["split"] = "training"
    elif change == "duplicate":
        doc["waypoints"][-1]["q"] = doc["waypoints"][0]["q"]
    elif change == "units":
        doc["units"] = "degrees"
    elif change == "order":
        doc["joint_names"] = list(reversed(doc["joint_names"]))
    elif change == "bounds":
        doc["waypoints"][-1]["q"] = [9] * 6
    elif change == "profile":
        doc["profile"]["width"] = 1288
    else:
        doc["role"] = "wrist"
    with pytest.raises((ValueError, model.ControlError)):
        routes.parse(doc, "third_left", profile.LIMITS)


@pytest.fixture(scope="module")
def run_evidence(tmp_path_factory):
    root = tmp_path_factory.mktemp("aprilgrid-run")
    (root / "images").mkdir()
    targets = route_document()
    detections, observations, _ = projected()
    offset = [0.01, -0.02, 0.127, 0.1, -0.2, 0.3]
    for i, (detection, item) in enumerate(zip(detections, observations)):
        image = render(detection)
        name = f"images/{i:03d}.png"
        assert cv2.imwrite(
            str(root / name), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        )
        base_tcp = np.asarray(item["T_base_flange"]) @ geometry.pose(offset)
        actual_tcp = tuple(
            np.r_[base_tcp[:3, 3], cv2.Rodrigues(base_tcp[:3, :3])[0].ravel()]
        )
        now = (i * 3 + 2) * 1_000_000_000
        state = model.State(
            tuple(targets["waypoints"][i]["q"]),
            (0.0,) * 6,
            now / 1e9,
            now,
            currents=(0.0,) * 6,
            tcp=tuple(map(float, actual_tcp)),
        )
        color = contracts.Provenance(
            "camera-test",
            i,
            contracts.SampleTime(now, "test", now + 10_000_000),
            True,
        )
        item.update(
            image=name,
            actual=dataclasses.asdict(state),
            color=dataclasses.asdict(color),
            exposure_monotonic_ns=now + 5_000_000,
            dwell={
                "start_receipt_ns": now - 1_000_000_000,
                "stop_receipt_ns": now + 1_000_000_000,
            },
        )
    document = {
        "schema_version": 2,
        "state": "complete",
        "simulated": True,
        "route": targets,
        "limits": dataclasses.asdict(profile.LIMITS),
        "camera": {"serial": "camera-test", "model": "D435IF", "profile": MODE},
        "tcp_offset": {
            "pose": offset,
            "source": "RTDEControlInterface.getTCPOffset",
        },
        "tcp_offset_after": offset,
        "observations": observations,
    }
    filesystem.write_json(root / "run.json", document)
    return root


def test_complete_pixel_pipeline_publishes_and_reverifies(
    run_evidence, tmp_path
):
    result = pipeline.solve(run_evidence, tmp_path / "bundle")
    assert len(result["solution"]["residuals"]) == 20
    assert pipeline.verify(tmp_path / "bundle") == result
    assert result["simulated"] and not result["active"]
    assert (
        max(r["translation_m"] for r in result["solution"]["residuals"])
        <= 0.002
    )
    (tmp_path / "bundle/images/000.png").write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        pipeline.verify(tmp_path / "bundle")


@pytest.mark.parametrize(
    "fault", ["stale", "moving", "offset", "target_as_flange", "predwell"]
)
def test_raw_readback_checks(run_evidence, fault):
    document = json.loads((run_evidence / "run.json").read_text())
    item = copy.deepcopy(document["observations"][0])
    if fault == "stale":
        item["actual"]["received_ns"] -= 100_000_000
    elif fault == "moving":
        item["actual"]["qd"][0] = 0.1
    elif fault == "offset":
        document["tcp_offset"]["pose"] = [0] * 6
    elif fault == "predwell":
        item["exposure_monotonic_ns"] = 0
    else:
        item["T_base_flange"] = np.eye(4).tolist()
    with pytest.raises(ValueError):
        pipeline.readback(item, profile.LIMITS, document["tcp_offset"]["pose"])


def test_intrinsics_never_see_validation_pixels(monkeypatch):
    detections, observations, _ = projected()
    monkeypatch.setattr(intrinsic, "_extrinsics", lambda *_: {})
    reference = intrinsic.solve(detections, observations, MODE, "third_left")
    for detection in detections[15:]:
        detection["image_points"] = [[0, 0]] * 96
    changed = intrinsic.solve(detections, observations, MODE, "third_left")
    assert changed["intrinsics"] == reference["intrinsics"]


def test_failed_solve_preserves_existing_result(run_evidence, tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "result.json"
    marker.write_text("previous calibration")
    with pytest.raises(FileExistsError):
        pipeline.solve(run_evidence, destination)
    assert marker.read_text() == "previous calibration"


def test_degenerate_camera_views_rejected():
    detections, observations, _ = projected()
    training = [copy.deepcopy(detections[0]) for _ in range(15)]
    with pytest.raises((ValueError, cv2.error)):
        intrinsic.solve(
            training + detections[15:], observations, MODE, "third_left"
        )


def test_original_pdf_render_uses_rotated_tags_and_metric_corner_order():
    from pathlib import Path

    image = cv2.imread(
        str(Path(__file__).parent / "fixtures/aprilgrid/printed-board.png")
    )
    detected = aprilgrid.detect(
        cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
        aprilgrid.Grid(),
        routes.DETECTION,
    )
    assert detected["tag_ids"] == list(range(24))
    objects = np.asarray(detected["object_points_m"])
    assert np.allclose(
        objects[:4],
        [[0.028, 0, 0], [0, 0, 0], [0, 0.028, 0], [0.028, 0.028, 0]],
    )
    pixels = np.asarray(detected["image_points"])
    # A flat PDF page has X right, Y up. Infer a map from three corners;
    # all 96 must agree within raster quantization, with negligible skew.
    anchors = [0, 28, 95]
    design = np.c_[objects[:, 0], -objects[:, 1], np.ones(len(objects))]
    mapping = np.linalg.solve(design[anchors], pixels[anchors])
    assert np.max(np.linalg.norm(design @ mapping - pixels, axis=1)) < 2
    assert mapping[0, 0] > 0 and mapping[1, 1] > 0
    assert abs(mapping[0, 1] / mapping[0, 0]) < 0.002
    assert abs(mapping[1, 0] / mapping[1, 1]) < 0.002
