"""Imported teaching, portable launch paths and verified activation boundaries."""

import math

import numpy as np
import pytest

from ur12e_collection import cli, filesystem, station
from ur12e_collection.calibration import (
    activation,
    aprilgrid,
    deployment,
    importing,
    pipeline,
    routes,
)
from ur12e_collection.simulation import profile
from test_aprilgrid_pipeline import route_document, run_evidence

# Shared pixel fixture exercises actual detection/solve, not a mocked result.
# pylint: disable=redefined-outer-name,unused-import


def taught():
    return {
        "camera_name": "camera_2",
        "camera_serial": "camera-test",
        "count": 30,
        "calibration_center_q": [2] * 6,
        "waypoints": [
            {
                "name": f"waypoint_{i:03}",
                "number": i,
                "actual_joints_rad": [q + i * 0.001 for q in profile.HOME],
            }
            for i in range(1, 31)
        ],
    }


def context():
    return {
        k: v
        for k, v in route_document().items()
        if k
        in (
            "role",
            "camera_serial",
            "camera_model",
            "robot_serial",
            "base_id",
            "mount_id",
            "board_mount_id",
            "board",
        )
    }


def test_import_preserves_actual_order_and_does_not_start_at_later_center():
    source = taught()
    route = importing.convert(source, context(), profile.LIMITS)
    assert route["start_q"] == source["waypoints"][0]["actual_joints_rad"]
    assert [p["q"] for p in route["waypoints"]] == [
        p["actual_joints_rad"] for p in source["waypoints"]
    ]
    assert [
        p["pose_id"] for p in route["waypoints"] if p["split"] == "validation"
    ] == [f"waypoint_{i:03}" for i in (6, 12, 18, 24, 30)]
    assert route["profile"] == {
        "width": 640,
        "height": 480,
        "fps": 30,
        "format": "rgb8",
    }


@pytest.mark.parametrize(
    "fault", ["serial", "order", "count", "nonfinite", "limit"]
)
def test_import_rejects_bad_measurements(fault):
    source = taught()
    if fault == "serial":
        source["camera_serial"] = "other"
    elif fault == "order":
        source["waypoints"].reverse()
    elif fault == "count":
        source["count"] = 29
    else:
        source["waypoints"][2]["actual_joints_rad"][0] = (
            math.nan if fault == "nonfinite" else 20
        )
    with pytest.raises((ValueError, RuntimeError)):
        importing.convert(source, context(), profile.LIMITS)


def test_native_profile_rejects_higher_resolution_without_resizing():
    document = route_document()
    document["profile"].update(width=1280, height=720)
    with pytest.raises(ValueError, match="640x480"):
        routes.parse(document, "third_left", profile.LIMITS)


def test_configured_grid_changes_layout_without_changing_old_default():
    original = aprilgrid.Grid().points([0, 4])
    assert np.allclose(
        original[:4],
        [[0.028, 0, 0], [0, 0, 0], [0, 0.028, 0], [0.028, 0.028, 0]],
    )
    alternate = aprilgrid.Grid(
        columns=3,
        rows=2,
        first_id=10,
        layout="top_down",
        marker_quarter_turns=0,
    )
    assert np.allclose(
        alternate.points([10])[:4],
        [[0, 0, 0], [0.028, 0, 0], [0.028, 0.028, 0], [0, 0.028, 0]],
    )
    with pytest.raises(ValueError):
        alternate.points([0])


def test_portable_deployment_paths_and_explicit_overrides(
    tmp_path, monkeypatch
):
    config = tmp_path / "calibration.json"
    filesystem.write_json(
        config,
        {
            "schema_version": 1,
            "output_root": "data",
            "routes": {"third_left": "left.json"},
        },
    )
    args = cli.parser().parse_args(
        [
            "cali",
            "--left",
            "--replay",
            "--calibration-config",
            str(config),
        ]
    )
    monkeypatch.chdir("/tmp")
    deployment.configure(args)
    assert args.poses == tmp_path / "left.json"
    assert args.output.parent == tmp_path / "data/third_left/runs"
    assert args.result_output.parent == tmp_path / "data/third_left/results"
    args.poses = tmp_path / "custom.json"
    deployment.configure(args)
    assert args.poses == tmp_path / "custom.json"


def test_preview_uses_actual_unwrapped_segments_and_ready_rates():
    route = routes.parse(route_document(), "third_left", profile.LIMITS)
    preview = deployment.preview(route, profile.LIMITS)
    assert (
        not preview["motion_ready"] and not preview["path_clearance_verified"]
    )
    assert len(preview["segments"]) == 20
    assert preview["nominal_total_s"] >= 40
    assert preview["speed_deg_s"] == math.degrees(profile.LIMITS.ready_speed)


def test_aprilgrid_activation_and_failed_verification_preserve_station(
    run_evidence,
    tmp_path,
):
    bundle = tmp_path / "result"
    value = pipeline.solve(run_evidence, bundle)
    config = station.example()
    config["cameras"]["third_left"]["serial"] = "camera-test"
    config["setup"] = {
        "simulated": True,
        "base_id": "base-test",
        "mounts": {
            "third_left": "mount-test",
            "third_right": "right",
            "wrist": "wrist",
        },
    }
    path = tmp_path / "station.json"
    filesystem.write_json(path, config)
    activated = activation.activate(bundle, path, "third_left")
    selected = activated["calibration"]["cameras"]["third_left"]
    assert selected["schema_version"] == 3
    assert selected["solution"] == value["solution"]
    assert selected["context"]["intrinsics"]["width"] == 640
    station.load(path)
    saved = path.read_bytes()
    with pytest.raises(ValueError, match="selected camera"):
        activation.activate(bundle, path, "third_right")
    assert path.read_bytes() == saved
    (bundle / "images/000.png").write_bytes(b"invalid")
    with pytest.raises(ValueError):
        activation.activate(bundle, path, "third_left")
    assert path.read_bytes() == saved


def test_activation_mismatched_setup_is_atomic(run_evidence, tmp_path):
    bundle = tmp_path / "result"
    pipeline.solve(run_evidence, bundle)
    path = tmp_path / "station.json"
    filesystem.write_json(path, station.example())
    original = path.read_bytes()
    with pytest.raises(ValueError, match="declared setup"):
        activation.activate(bundle, path, "third_left")
    assert path.read_bytes() == original
