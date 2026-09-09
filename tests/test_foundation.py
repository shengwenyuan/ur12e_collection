"""Verify failure semantics and data preservation, without real devices."""

import dataclasses
import json
from unittest import mock

import pytest

from ur12e_collection import cli
from ur12e_collection import contracts
from ur12e_collection import diagnostics
from ur12e_collection import station


def test_unimplemented_command_never_falls_back(capsys):
    """A requested physical workflow cannot silently run simulated collection."""
    with mock.patch("socket.socket", side_effect=AssertionError("network")):
        assert cli.main(["session"]) == 2
    assert "unavailable" in capsys.readouterr().err


def test_doctor_does_not_connect(tmp_path, capsys):
    """Default diagnostics preserve station contents and use no sockets."""
    path = tmp_path / "station.json"
    path.write_text("preserve me")
    with mock.patch("socket.socket", side_effect=AssertionError("network")):
        assert (
            cli.main(
                [
                    "doctor",
                    "--format",
                    "json",
                    "--require-mounts",
                    "--config-dir",
                    str(tmp_path),
                    "--data-dir",
                    str(tmp_path),
                ]
            )
            == 0
        )
    report = json.loads(capsys.readouterr().out)
    assert report["hardware"] == {"state": "not_checked", "motion_ready": False}
    assert path.read_text() == "preserve me"
    assert list(tmp_path.iterdir()) == [path]


def test_missing_mount_is_explicit(tmp_path):
    """Diagnostics never create a missing persistent directory."""
    missing = tmp_path / "absent"
    assert diagnostics.mount(missing)["state"] == "unavailable"
    assert not missing.exists()


def test_station_draft_is_not_camera_ready():
    """Unknown identities can be edited but cannot pass camera readiness."""
    draft = station.example()
    station.validate(draft)
    with pytest.raises(ValueError, match="all three"):
        station.validate(draft, cameras_ready=True)


def test_camera_identity_validation():
    """Every required role must retain its own configured device."""
    draft = station.example()
    for index, camera in enumerate(draft["cameras"].values()):
        camera["serial"] = str(index)
    station.validate(draft, cameras_ready=True)
    draft["cameras"]["third_right"]["serial"] = "0"
    with pytest.raises(ValueError, match="unique"):
        station.validate(draft)


def test_atomic_station_replacement(tmp_path):
    """Invalid or interrupted updates preserve the last valid configuration."""
    path = tmp_path / "station.json"
    draft = station.example()
    station.write(path, draft)
    previous = path.read_bytes()
    with pytest.raises(FileExistsError):
        station.write(path, draft)
    with mock.patch("os.replace", side_effect=OSError("interrupted")):
        with pytest.raises(OSError, match="interrupted"):
            station.write(path, draft, replace=True)
    assert path.read_bytes() == previous
    draft["ur"]["ready_q_rad"] = [float("nan")] * 6
    with pytest.raises(ValueError):
        station.write(path, draft, replace=True)
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


def test_configuration_cli_uses_shared_schema(tmp_path):
    """Initialization produces a draft; existing files survive reinitialization."""
    path = tmp_path / "station.json"
    assert cli.main(["station", "initialize", "--output", str(path)]) == 0
    assert cli.main(["station", "validate", str(path)]) == 0
    assert cli.main(["station", "validate", str(path), "--cameras-ready"]) == 1
    previous = path.read_bytes()
    assert cli.main(["station", "initialize", "--output", str(path)]) == 1
    assert path.read_bytes() == previous


def test_invalid_profile_rejected():
    """Unsupported profile changes must not enter a station configuration."""
    draft = station.example()
    draft["camera_profile"]["fps"] = 60
    with pytest.raises(station.jsonschema.ValidationError):
        station.validate(draft)


def test_data_semantics_are_distinct():
    """Intent, issued command, and actual feedback retain different values."""
    provenance = contracts.Provenance(
        "fixture", 1, contracts.SampleTime(None, "unknown", 123), True
    )
    leader = contracts.LeaderIntent(provenance, (1.0,) * 6, 200)
    command = contracts.SentCommand(provenance, (0.5,) * 6, 150)
    follower = contracts.FollowerState(provenance, None, None)
    assert len({type(leader), type(command), type(follower)}) == 3
    assert leader.gripper_request_raw == 200
    assert command.joint_positions_rad != leader.joint_positions_rad
    serialized = json.loads(json.dumps(dataclasses.asdict(follower)))
    assert serialized["kind"] == "follower_state"
    assert serialized["schema_version"] == 1
    assert serialized["joint_positions_rad"] is None
    assert serialized["gripper_position_raw"] is None
    assert serialized["provenance"]["time"]["source_ns"] is None
    assert serialized["provenance"]["simulated"] is True


@pytest.mark.parametrize("raw", [-1, 256, 0.5, True])
def test_raw_gripper_range(raw):
    """Register positions cannot be normalized or silently converted."""
    provenance = contracts.Provenance(
        "fixture", 0, contracts.SampleTime(0, "device", 1)
    )
    with pytest.raises(ValueError):
        contracts.FollowerState(provenance, None, raw)


def test_nonfinite_joint_data_rejected():
    """Non-finite joint positions cannot propagate through the shared contract."""
    provenance = contracts.Provenance(
        "fixture", 0, contracts.SampleTime(0, "device", 1)
    )
    with pytest.raises(ValueError):
        contracts.LeaderIntent(provenance, (float("inf"),) * 6, None)
