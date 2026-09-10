"""Immutable calibration activation and setup changes preserve old evidence."""

import copy
import dataclasses
import json
import os
from unittest import mock

import pytest

from ur12e_collection import cli, snapshots, station, synthetic
from ur12e_collection.calibration import results
from test_calibration import LIMITS, observations


@pytest.fixture
def calibration_input(tmp_path):
    def create(role="wrist"):
        round_name = "wrist" if role == "wrist" else "fixed"
        data, _, _ = observations(round_name)
        document = {
            "schema_version": 1,
            "simulated": True,
            "role": role,
            "camera_serial": role,
            "base_id": "base-1",
            "mount_id": role + "-1",
            "script_revision": "synthetic-geometry-fixture",
            "board": {
                "squares_x": 7,
                "squares_y": 5,
                "square_m": 0.03,
                "marker_m": 0.022,
                "dictionary": "DICT_4X4_50",
            },
            "intrinsics": synthetic.observations(synthetic.configuration())[
                role
            ]["color_intrinsics"],
            "thresholds": dataclasses.asdict(LIMITS),
            "detection_limits": {
                "sharpness": 10,
                "coverage": 0.01,
                "reprojection_px": 1,
                "ambiguity_gap_px": 0.1,
            },
            "observations": [
                {
                    "pose_id": item.pose_id,
                    "split": "training" if i < 12 else "validation",
                    "T_base_flange": item.base_flange.tolist(),
                    "T_camera_board": item.camera_board.tolist(),
                    "reprojection_px": item.reprojection_px,
                }
                for i, item in enumerate(data)
            ],
        }
        path = tmp_path / (role + ".json")
        path.write_text(json.dumps(document))
        return path

    return create


@pytest.fixture
def configured(tmp_path):
    path = tmp_path / "station.json"
    station.write(path, synthetic.configuration())
    setup = {
        "base_id": "base-1",
        "simulated": True,
        "mounts": {
            role: role + "-1" for role in ("wrist", "third_left", "third_right")
        },
    }
    results.declare(path, setup)
    return path, setup


def test_two_round_results_activate_and_mount_change_preserves_wrist(
    tmp_path, calibration_input, configured, snapshot
):
    path, setup = configured
    for role in ("wrist", "third_left"):
        bundle = tmp_path / role
        value = results.solve(calibration_input(role), bundle)
        assert results.verify(bundle) == value
        results.activate(bundle, path)
    config = station.load(path)
    frozen = snapshots.build(
        config,
        synthetic.observations(config),
        {
            key: snapshot[key]
            for key in (
                "task",
                "software_revision",
                "clock_epoch",
                "clock_id",
                "clock_basis",
                "clock_validated",
                "simulated",
            )
        },
    )
    previous = copy.deepcopy(frozen)
    setup["mounts"]["third_left"] = "left-moved"
    updated = results.declare(path, setup)
    assert set(updated["calibration"]["cameras"]) == {"wrist"}
    assert snapshots.copy(frozen) == previous
    with pytest.raises(ValueError, match="identity"):
        results.activate(tmp_path / "third_left", path)
    setup["base_id"] = "base-moved"
    assert results.declare(path, setup)["calibration"] is None


@pytest.mark.parametrize(
    "change", ["evidence", "result", "simulation", "camera"]
)
def test_invalid_activation_preserves_station_bytes(
    tmp_path, calibration_input, configured, change
):
    path, setup = configured
    bundle = tmp_path / "result"
    results.solve(calibration_input(), bundle)
    if change in ("evidence", "result"):
        file = bundle / (
            "input.json" if change == "evidence" else "result.json"
        )
        data = json.loads(file.read_text())
        if change == "evidence":
            data["observations"][-1]["T_camera_board"][0][3] += 0.05
        else:
            data["solution"]["T_flange_camera"][0][3] += 0.05
        file.write_text(json.dumps(data))
    elif change == "simulation":
        setup["simulated"] = False
        results.declare(path, setup)
    else:
        config = station.load(path)
        config["cameras"]["wrist"]["serial"] = "different"
        station.write(path, config, replace=True)
    previous = path.read_bytes()
    with pytest.raises(ValueError):
        results.activate(bundle, path)
    assert path.read_bytes() == previous


def test_directory_sync_failure_restores_previous_configuration(
    tmp_path, calibration_input, configured
):
    path, _ = configured
    bundle = tmp_path / "result"
    results.solve(calibration_input(), bundle)
    previous = path.read_bytes()
    native = os.fsync

    def fail_directory(descriptor):
        import stat

        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("directory sync failure")
        return native(descriptor)

    with mock.patch.object(station.os, "fsync", side_effect=fail_directory):
        with pytest.raises(OSError, match="sync failure"):
            results.activate(bundle, path)
    assert path.read_bytes() == previous


def test_physical_input_requires_real_images_and_cli_has_no_network(
    tmp_path, calibration_input, configured, capsys
):
    source = calibration_input()
    value = json.loads(source.read_text())
    value["simulated"] = False
    source.write_text(json.dumps(value))
    with mock.patch("socket.socket", side_effect=AssertionError("network")):
        assert (
            cli.main(
                [
                    "calibrate",
                    "solve",
                    str(source),
                    "--output",
                    str(tmp_path / "physical"),
                ]
            )
            == 1
        )
    assert "requires image evidence" in capsys.readouterr().err
    assert not (tmp_path / "physical").exists()


def test_snapshot_rejects_changed_optics(
    tmp_path, calibration_input, configured, snapshot
):
    path, _ = configured
    bundle = tmp_path / "result"
    results.solve(calibration_input(), bundle)
    config = results.activate(bundle, path)
    observed = synthetic.observations(config)
    observed["wrist"]["color_intrinsics"]["fx"] += 1
    context = {
        key: snapshot[key]
        for key in (
            "task",
            "software_revision",
            "clock_epoch",
            "clock_id",
            "clock_basis",
            "clock_validated",
            "simulated",
        )
    }
    with pytest.raises(ValueError, match="optics"):
        snapshots.build(config, observed, context)


@pytest.mark.parametrize("role", ["wrist", "third_left"])
def test_rendered_png_bundle_redetects_and_rejects_tampering(
    tmp_path, calibration_input, role
):
    import cv2
    import numpy as np
    from ur12e_collection.calibration import geometry
    from test_calibration import image_fixture

    path = calibration_input(role)
    document = json.loads(path.read_text())
    document["thresholds"] = dataclasses.asdict(
        geometry.Thresholds(0.025, 0.1, 1)
    )
    document["detection_limits"]["ambiguity_gap_px"] = 0.005
    camera = geometry.pose([0.04, -0.03, 0.08, 0.2, -0.1, 0.3])
    constant = geometry.pose([0.6, -0.2, 0.4, -0.1, 0.2, 0.4])
    random = np.random.default_rng(915)
    for item in document["observations"]:
        camera_board = geometry.pose(
            np.r_[
                [-0.10, -0.07, random.uniform(0.42, 0.55)],
                random.uniform([0.2, -0.5, -0.2], [0.55, 0.3, 0.2]),
            ]
        )
        image, _, optics, _ = image_fixture(camera_board)
        document["intrinsics"] = optics
        robot = (
            constant @ geometry.inverse(camera_board) @ geometry.inverse(camera)
            if role == "wrist"
            else camera @ camera_board @ geometry.inverse(constant)
        )
        item["T_base_flange"] = robot.tolist()
        del item["T_camera_board"], item["reprojection_px"]
        item["image"] = "images/" + item["pose_id"] + ".png"
        target = path.parent / item["image"]
        target.parent.mkdir(exist_ok=True)
        assert cv2.imwrite(str(target), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    path.write_text(json.dumps(document))
    bundle = tmp_path / "rendered"
    value = results.solve(path, bundle)
    assert results.verify(bundle) == value
    assert len(value["detections"]) == 16
    target = bundle / document["observations"][0]["image"]
    target.write_bytes(b"corrupt PNG")
    with pytest.raises(ValueError, match="decoded"):
        results.verify(bundle)


def test_station_updates_serialize_read_modify_replace(configured):
    import concurrent.futures
    import time

    path, _ = configured
    config = station.load(path)
    config["station_id"] = "0"
    station.write(path, config, replace=True)

    def increment(_):
        def change(current):
            number = int(current["station_id"])
            time.sleep(0.005)
            current["station_id"] = str(number + 1)
            return current

        station.update(path, change)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment, range(12)))
    assert station.load(path)["station_id"] == "12"
