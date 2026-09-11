"""Calibration cannot hide HOME errors, wrap branches or fabricate readiness."""

import dataclasses
import json
import math

import pytest

from ur12e_collection.leader import mapping


def calibration():
    return mapping.Calibration(
        (0, -math.pi / 2, -math.pi / 2, -math.pi / 2, math.pi / 2, 0),
        tuple(
            mapping.Joint(2048, sign, 1024, 3072)
            for sign in (1, -1, 1, -1, 1, -1)
        ),
        3200,
        3800,
        "test-only fixture",
        "a" * 64,
    )


def test_mapping_keeps_calibrated_home_signs_and_absolute_target():
    c = calibration()
    raw = (2048,) * 6 + (3200,)
    assert c.angles(raw) == c.home_rad
    actual = c.angles((2058,) * 6 + (3200,))
    for i, q in enumerate(actual):
        assert q - c.home_rad[i] == pytest.approx(
            (1 if i % 2 == 0 else -1) * 10 * mapping.RADIANS_PER_COUNT
        )
    assert c.angles(raw) == c.home_rad


def test_calibration_requires_verified_shapes_and_does_not_wrap():
    c = calibration()
    for value in (-1, 4096 + 2048, True):
        with pytest.raises(ValueError):
            c.angles((value,) * 6 + (3200,))
    for sign in (0, 2, True):
        with pytest.raises(ValueError):
            mapping.Joint(2048, sign, 0, 4095)
    with pytest.raises(ValueError):
        dataclasses.replace(c, evidence_sha256="unknown")
    with pytest.raises(ValueError):
        dataclasses.replace(c, gripper_open=c.gripper_closed)


def test_gripper_assigned_range_saturates_in_both_directions():
    c = calibration()
    assert [c.gripper(r) for r in (3200, 3500, 3800)] == [0, 128, 255]
    reverse = dataclasses.replace(c, gripper_open=3800, gripper_closed=3200)
    assert reverse.gripper(3200) == 255
    assert c.gripper(3801) == 255
    assert c.gripper(3100) == 0
    assert reverse.gripper(3100) == 255
    assert reverse.gripper(3900) == 0


def test_file_round_trip_preserves_fixed_mapping_and_rejects_offsets(tmp_path):
    path = tmp_path / "calibration.json"
    c = calibration()
    c.save(path)
    assert mapping.load(path) == c
    with pytest.raises(FileExistsError):
        c.save(path)
    value = json.loads(path.read_text())
    value["episode_offset"] = [0] * 6
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="unexpected"):
        mapping.load(path)


def test_stable_reference_does_not_claim_physical_home(tmp_path):
    path = tmp_path / "samples.jsonl"
    rows = [
        dict(
            sequence=i,
            start_ns=i * 20_000_000,
            end_ns=i * 20_000_000 + 1_000_000,
            position=[2048 + i % 2] * 7,
            errors=[0] * 7,
        )
        for i in range(61)
    ]

    def write():
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    write()
    result = mapping.reference(path)
    assert result["spread_counts"] == [1] * 7
    assert result["physical_reference_confirmed"] is False
    rows[-1]["position"][0] += 20
    write()
    with pytest.raises(ValueError, match="two encoder"):
        mapping.reference(path)
    rows[-1]["position"][0] = 2048
    rows[-1]["start_ns"] = rows[-2]["start_ns"]
    write()
    with pytest.raises(ValueError, match="stale"):
        mapping.reference(path)


def test_calibration_is_independent_of_episode_mode(tmp_path, capsys):
    from ur12e_collection import cli

    path = tmp_path / "calibration.json"
    c = calibration()
    c.save(path)
    document = json.loads(path.read_text())
    assert document["schema_version"] == 3
    assert document["kind"] == "leader_joint_calibration"
    assert "mapping" not in document
    assert cli.main(["calibrate", "leader-validate", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["motion_ready"] is False
    assert report["calibration_id"] == c.identity()
    old = document.copy()
    old["schema_version"] = 1
    old["mapping"] = "fixed_absolute"
    del old["kind"]
    path.write_text(json.dumps(old))
    with pytest.raises(ValueError):
        mapping.load(path)
    assert (
        dataclasses.replace(c, reference="another reference").identity()
        != c.identity()
    )


def test_persistent_trace_calibration_rejects_epoch_changes(tmp_path):
    path = tmp_path / "samples.jsonl"
    rows = [
        dict(
            epoch="read-session",
            sequence=i,
            start_ns=i * 20_000_000,
            end_ns=i * 20_000_000 + 1,
            position=[2048] * 7,
            velocity_raw=[0] * 7,
            errors=[0] * 7,
        )
        for i in range(61)
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert mapping.reference(path)["motion_ready"] is False
    rows[-1]["epoch"] = "reconnected"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ValueError, match="epochs"):
        mapping.reference(path)


def test_reference_uses_actual_last_sample_not_an_average(tmp_path):
    path = tmp_path / "samples.jsonl"
    rows = [
        dict(
            sequence=i,
            start_ns=i * 20_000_000,
            end_ns=i * 20_000_000 + 1,
            position=[2048] * 7,
            errors=[0] * 7,
        )
        for i in range(61)
    ]
    rows[-1]["position"] = [2049] * 7
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    value = mapping.reference(path)
    assert value["home_counts"] == rows[-1]["position"]
    assert value["reference_sample"] == rows[-1]
    assert (
        value["reference_selection"] == "last_actual_sample_in_stable_capture"
    )


def test_signed_teaching_coordinates_do_not_wrap_or_change_physical_bounds():
    c = dataclasses.replace(
        calibration(),
        joints=tuple(mapping.Joint(42, 1, -600, 600) for _ in range(6)),
        gripper_open=3256,
        gripper_closed=3388,
    )
    for count in (-433, -1, 0, 42, 308):
        assert c.angles((count,) * 6 + (3256,))[0] == pytest.approx(
            (count - 42) * mapping.RADIANS_PER_COUNT
        )
    with pytest.raises(ValueError):
        c.angles((4096 + 42,) * 6 + (3256,))
    assert [c.gripper(v) for v in (2500, 3256, 3322, 3388, 3500)] == [
        0,
        0,
        128,
        255,
        255,
    ]


def test_powered_coordinates_require_a_new_binding_after_reset():
    from ur12e_collection.leader.coordinates import PoweredAxis

    bound = PoweredAxis("torque-1", -433, 3663, 0, 4095)
    assert bound.goal(-433, "torque-1") == 3663
    assert bound.goal(-400, "torque-1") == 3696
    with pytest.raises(ValueError, match="epoch"):
        bound.goal(-433, "torque-2")
    with pytest.raises(ValueError, match="interval"):
        bound.goal(308, "torque-1")
    rebound = PoweredAxis("torque-2", 308, 308, 0, 4095)
    assert rebound.goal(308, "torque-2") == 308
    with pytest.raises(ValueError):
        PoweredAxis("torque-1", -433, -433, 0, 4095)
