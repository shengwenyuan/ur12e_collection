"""Physical recording composition and launcher configuration without devices."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from ur12e_collection import synthetic
from ur12e_collection.physical import recording
from test_physical_teleop import configuration


def test_resources_bind_devices_and_start_only_cameras_before_sdk(
    tmp_path, monkeypatch
):
    config = configuration()
    station = synthetic.configuration()
    station["ur"].update(
        host=config["follower"]["host"], serial=config["follower"]["serial"]
    )
    station["hande"].update(host=config["follower"]["host"], port=63352)
    monkeypatch.setattr(recording.station, "load", lambda *a, **k: station)
    recorder, feedback = mock.Mock(), mock.Mock()
    monkeypatch.setattr(recording.recording, "Recorder", recorder)
    monkeypatch.setattr(recording.feedback, "Feedback", feedback)
    options = recording.Options(tmp_path / "station.json", tmp_path, "test")
    resources = recording.Resources(config, options, "sha256:test")
    resources.start()
    feedback.return_value.start.assert_not_called()
    context = recorder.call_args.args[1]
    assert context["simulated"] is False
    assert context["control"]["inputs"]["gripper"]["force"] == 32
    assert context["control"]["feedback_hz"] == 125
    assert (
        recorder.call_args.args[0]["gello"]["backend"] == "dynamixel_readonly"
    )
    resources.close()
    config["follower"]["serial"] = "another-device"
    with pytest.raises(ValueError, match="differ from controlled"):
        recording.Resources(config, options, "sha256:test")


def launcher():
    path = Path(__file__).parents[1] / "scripts/teleop.py"
    spec = importlib.util.spec_from_file_location("test_teleop_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recording_launcher_mounts_usb_and_output_and_pins_image(
    tmp_path, monkeypatch
):
    module = launcher()
    value = configuration()
    device = tmp_path / "leader"
    device.touch()
    value["leader"]["device"] = str(device)
    value["follower"]["serial"] = "launcher-offline-test"
    value["evidence"] = tmp_path / "evidence"
    station = tmp_path / "station.json"
    station.write_text("{}")
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "teleop",
            "--config",
            "unused.json",
            "--image",
            "test-image",
            "--operator-approved",
            "--record-station",
            str(station),
            "--record-output",
            str(tmp_path / "data"),
            "--task",
            "offline fixture",
        ],
    )
    monkeypatch.setattr(module.config, "load", lambda _: value)
    monkeypatch.setattr(module.network, "check", mock.Mock())
    run = mock.Mock(
        side_effect=[
            SimpleNamespace(stdout="sha256:fixed\n"),
            SimpleNamespace(returncode=0),
        ]
    )
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0
    args = run.call_args.args[0]
    assert args[args.index("--memory") + 1] == "8g"
    assert args[args.index("--shm-size") + 1] == "512m"
    assert args[args.index("--entrypoint") + 2] == "sha256:fixed"
    assert "/dev/bus/usb" in args
    assert f"{tmp_path / 'data'}:{tmp_path / 'data'}:rw" in args
    assert args[-2:] == ["--task", "offline fixture"]


def test_camera_exposure_selects_realsense_video_nodes(tmp_path):
    for node, label in (("video0", "Intel RealSense"), ("video1", "Webcam")):
        entry = tmp_path / node
        entry.mkdir()
        (entry / "name").write_text(label)
    assert launcher().camera_devices(tmp_path) == [
        "--device",
        "/dev/bus/usb",
        "--device",
        "/dev/video0",
    ]
