"""Known geometry, independent poses and actual image detection for M12."""

import dataclasses

import cv2
import numpy as np
import pytest

from ur12e_collection.calibration import board, checkpoint, geometry
from ur12e_collection.control import model
from ur12e_collection.simulation import profile

LIMITS = geometry.Thresholds(0.002, 0.02, 1.0)


def observations(round_name):
    random = np.random.default_rng(917)
    camera = geometry.pose([0.04, -0.03, 0.08, 0.2, -0.1, 0.3])
    constant = geometry.pose([0.6, -0.2, 0.4, -0.1, 0.2, 0.4])
    result = []
    for index in range(16):
        robot = geometry.pose(
            np.r_[random.uniform(-0.4, 0.4, 3), random.uniform(-0.8, 0.8, 3)]
        )
        observed = (
            geometry.inverse(camera) @ geometry.inverse(robot) @ constant
            if round_name == "wrist"
            else geometry.inverse(camera) @ robot @ constant
        )
        result.append(geometry.Observation(str(index), robot, observed, 0.1))
    return result, camera, constant


@pytest.mark.parametrize("round_name", ["fixed", "wrist"])
def test_both_transform_directions_recover_known_geometry(round_name):
    data, camera, constant = observations(round_name)
    result = geometry.solve(round_name, data[:12], data[12:], LIMITS)
    actual = result[
        "T_flange_camera" if round_name == "wrist" else "T_base_camera"
    ]
    other = result[
        "T_base_board" if round_name == "wrist" else "T_flange_board"
    ]
    assert np.allclose(actual, camera, atol=1e-8)
    assert np.allclose(other, constant, atol=1e-8)
    assert (
        len([r for r in result["residuals"] if r["split"] == "validation"]) == 4
    )


@pytest.mark.parametrize("round_name", ["fixed", "wrist"])
def test_held_out_error_cannot_be_fit_away(round_name):
    data, _, _ = observations(round_name)
    changed = data[-1].camera_board.copy()
    changed[0, 3] += 0.03
    data[-1] = dataclasses.replace(data[-1], camera_board=changed)
    with pytest.raises(ValueError, match="validation"):
        geometry.solve(round_name, data[:12], data[12:], LIMITS)


def test_degenerate_pose_set_and_duplicate_ids_rejected():
    data, _, _ = observations("wrist")
    with pytest.raises(ValueError, match="unique"):
        geometry.solve("wrist", data[:12], data[11:15], LIMITS)
    robot = geometry.pose([0, 0, 0, 0, 0, 0])
    data = [dataclasses.replace(item, base_flange=robot) for item in data]
    with pytest.raises(ValueError, match="rotation axes"):
        geometry.solve("wrist", data[:12], data[12:], LIMITS)


@pytest.mark.parametrize(
    "bad", [np.zeros((4, 4)), np.diag([-1, 1, 1, 1]), np.full((4, 4), np.nan)]
)
def test_invalid_transform_rejected(bad):
    with pytest.raises(ValueError, match="transform"):
        geometry.transform(bad)


def image_fixture(camera_board=None):
    definition = board.Board(7, 5, 0.03, 0.022, "DICT_4X4_50")
    intrinsics = {
        "width": 640,
        "height": 480,
        "fx": 600,
        "fy": 600,
        "ppx": 320,
        "ppy": 240,
        "model": "none",
        "coeffs": [],
    }
    if camera_board is None:
        camera_board = geometry.pose([-0.10, -0.07, 0.5, 0.25, -0.2, 0.1])
    points = np.array(
        [[0, 0, 0], [0.21, 0, 0], [0.21, 0.15, 0], [0, 0.15, 0]], np.float32
    )
    matrix, distortion = board.optics(intrinsics)
    pixels = cv2.projectPoints(
        points,
        cv2.Rodrigues(camera_board[:3, :3])[0],
        camera_board[:3, 3],
        matrix,
        distortion,
    )[0].reshape(-1, 2)
    homography = cv2.getPerspectiveTransform(
        np.array([[0, 0], [699, 0], [699, 499], [0, 499]], np.float32), pixels
    )
    gray = cv2.warpPerspective(
        definition.create().generateImage((700, 500)),
        homography,
        (640, 480),
        borderValue=255,
    )
    return (
        cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB),
        definition,
        intrinsics,
        camera_board,
    )


def test_detect_real_charuco_pixels_with_known_pose():
    image, definition, intrinsics, expected = image_fixture()
    result = board.detect(
        image, definition, intrinsics, board.DetectionLimits(20, 0.02, 1, 0.03)
    )
    residual = geometry.error(expected, result["T_camera_board"])
    assert residual["translation_m"] < 0.005
    assert residual["rotation_rad"] < 0.04
    assert result["reprojection_px"] < 1


@pytest.mark.parametrize("failure", ["blank", "blur", "distortion"])
def test_detection_rejects_bad_images_or_optics(failure):
    image, definition, intrinsics, _ = image_fixture()
    if failure == "blank":
        image[:] = 255
    elif failure == "blur":
        image = cv2.GaussianBlur(image, (61, 61), 20)
    else:
        intrinsics["model"] = "inverse_brown_conrady"
    with pytest.raises(ValueError):
        board.detect(
            image,
            definition,
            intrinsics,
            board.DetectionLimits(20, 0.02, 1, 0.03),
        )


def state(now, **changes):
    return dataclasses.replace(
        model.State(profile.HOME, (0.0,) * 6, now / 1e9, now), **changes
    )


def test_two_second_checkpoint_excludes_moving_and_boundary_images():
    gate = checkpoint.Checkpoint("pose-1", profile.HOME, profile.LIMITS)
    gate.update(state(0, qd=(0.1,) * 6), 0)
    assert not gate.image(0, state(0))
    for now in range(100_000_000, 2_300_000_000, 100_000_000):
        gate.update(state(now), now)
        gate.image(now, state(now))
    assert gate.start_ns == 200_000_000
    assert not gate.image(2_200_000_000, state(2_200_000_000))
    result = gate.finish(2_200_000_000)
    assert (
        result["stop_receipt_ns"] - result["start_receipt_ns"] == 2_000_000_000
    )


@pytest.mark.parametrize("failure", ["moving", "stale", "future_pose"])
def test_checkpoint_failure_latches(failure):
    gate = checkpoint.Checkpoint("pose-1", profile.HOME, profile.LIMITS)
    gate.update(state(0), 0)
    gate.update(state(100_000_000), 100_000_000)
    with pytest.raises(model.ControlError):
        if failure == "moving":
            gate.update(state(150_000_000, qd=(0.1,) * 6), 150_000_000)
        elif failure == "stale":
            gate.update(state(100_000_000), 500_000_000)
        else:
            gate.image(150_000_000, state(151_000_000))
    assert gate.state == "failed"


@pytest.mark.parametrize("round_name", ["fixed", "wrist"])
def test_small_measurement_noise_reports_nonzero_residuals(round_name):
    data, camera, _ = observations(round_name)
    random = np.random.default_rng(44)
    noisy = []
    for item in data:
        perturbation = geometry.pose(
            np.r_[random.normal(0, 0.00005, 3), random.normal(0, 0.0001, 3)]
        )
        noisy.append(
            dataclasses.replace(
                item, camera_board=item.camera_board @ perturbation
            )
        )
    result = geometry.solve(round_name, noisy[:12], noisy[12:], LIMITS)
    field = "T_flange_camera" if round_name == "wrist" else "T_base_camera"
    assert geometry.error(camera, result[field])["translation_m"] < 0.002
    assert max(row["translation_m"] for row in result["residuals"]) > 0.00001


def test_single_axis_motion_is_not_observable():
    data, _, _ = observations("wrist")
    data = [
        dataclasses.replace(
            item, base_flange=geometry.pose([0.01 * i, 0, 0, 0, 0, 0.1 * i])
        )
        for i, item in enumerate(data)
    ]
    with pytest.raises(ValueError, match="rotation axes"):
        geometry.solve("wrist", data[:12], data[12:], LIMITS)
