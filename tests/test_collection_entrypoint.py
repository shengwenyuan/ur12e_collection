"""Installed operator commands delegate in process before opening hardware."""

import json
from pathlib import Path
from unittest import mock

import pytest

from ur12e_collection import operator


@pytest.fixture
def entrypoint(tmp_path, monkeypatch):
    config = tmp_path / "configuration"
    config.mkdir()
    (config / "teleop.ur.json").write_text("{}")
    (config / "recording.station.json").write_text("{}")
    (config / "task-routes.json").write_text(
        json.dumps({"Pick up the red block.": "red-block"})
    )
    monkeypatch.setenv("UR12E_CONFIG_DIR", str(config))
    monkeypatch.setenv("UR12E_DATA_DIR", str(tmp_path / "captures"))
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(operator.cli, "main", mock.Mock(return_value=0))
    monkeypatch.setattr(operator.commands, "run", mock.Mock(return_value=0))
    monkeypatch.setattr(
        operator.configuration,
        "load",
        mock.Mock(
            return_value={
                "follower": {
                    "backend": "ur",
                    "host": "station",
                    "interface": "enp3s0",
                }
            }
        ),
    )
    monkeypatch.setattr(
        operator.network, "check", mock.Mock(return_value={"ok": True})
    )
    return operator


@pytest.mark.parametrize("output", [None, "new captures", "~/custom"])
def test_recording_delegates_in_process(entrypoint, tmp_path, output):
    argv = ["gello"] + (["--output", output] if output else [])
    with mock.patch("subprocess.run", side_effect=AssertionError("nested run")):
        assert entrypoint.main(argv) == 0
    command = entrypoint.cli.main.call_args.args[0]
    args = entrypoint.cli.parser().parse_args(command)
    assert args.config == tmp_path / "configuration/teleop.ur.json"
    assert (
        args.record_station == tmp_path / "configuration/recording.station.json"
    )
    expected = Path(output) if output else tmp_path / "captures"
    assert args.record_output == expected.expanduser().resolve() / "red-block"
    assert args.operator_approved and not args.preflight
    assert args.task == "Pick up the red block."
    assert not args.record_output.exists()
    entrypoint.network.check.assert_called_once_with("station", "enp3s0")


@pytest.mark.parametrize(
    "argv",
    [["--help"], ["gello", "--help"], ["cali", "--help"], ["dagger"], []],
)
def test_help_and_unknown_modes_never_launch(entrypoint, argv):
    with pytest.raises(SystemExit) as result:
        entrypoint.main(argv)
    assert result.value.code == (0 if "--help" in argv else 2)
    entrypoint.cli.main.assert_not_called()
    entrypoint.network.check.assert_not_called()
    entrypoint.commands.run.assert_not_called()


@pytest.mark.parametrize(
    "filename", ["teleop.ur.json", "recording.station.json"]
)
def test_missing_station_never_launches(entrypoint, tmp_path, capsys, filename):
    (tmp_path / "configuration" / filename).unlink()
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 2
    assert "missing station configuration" in capsys.readouterr().err
    entrypoint.cli.main.assert_not_called()


def test_configuration_overrides(entrypoint, tmp_path):
    profile = tmp_path / "other-profile.json"
    station = tmp_path / "other-station.json"
    profile.write_text("{}")
    station.write_text("{}")
    entrypoint.main(
        ["gello", "--config", str(profile), "--station", str(station)]
    )
    args = entrypoint.cli.parser().parse_args(
        entrypoint.cli.main.call_args.args[0]
    )
    assert args.config == profile and args.record_station == station


def test_owner_exit_is_preserved(entrypoint):
    entrypoint.cli.main.return_value = 7
    assert entrypoint.main(["gello"]) == 7


def test_network_mismatch_never_launches(entrypoint):
    entrypoint.network.check.side_effect = ValueError("wrong interface")
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 2
    entrypoint.cli.main.assert_not_called()


def test_task_choice_retries_and_preserves_description(
    entrypoint, tmp_path, capsys
):
    route = tmp_path / "routes.json"
    description = "Put the red block in the small box, then withdraw the arm."
    route.write_text(
        json.dumps({"Other task": "other", description: "red-box"})
    )
    with mock.patch("builtins.input", side_effect=["bad", "0", "3", "2"]):
        entrypoint.main(["gello", "--task-routes", str(route)])
    args = entrypoint.cli.parser().parse_args(
        entrypoint.cli.main.call_args.args[0]
    )
    assert args.task == description
    assert args.record_output == tmp_path / "captures/red-box"
    text = capsys.readouterr().out
    assert "Collection mode: GELLO" in text and description in text


@pytest.mark.parametrize("answer", [EOFError, KeyboardInterrupt, "q"])
def test_cancel_selection_never_launches(entrypoint, answer):
    with mock.patch("builtins.input") as read:
        if isinstance(answer, str):
            read.return_value = answer
        else:
            read.side_effect = answer
        with pytest.raises(SystemExit) as result:
            entrypoint.main(["gello"])
    assert result.value.code == 0
    entrypoint.cli.main.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        "{}",
        "[]",
        "null",
        "{",
        '{"task": "good", "task": "other"}',
        '{"task": "same", "other": "SAME"}',
        '{"": "empty"}',
        '{"task": "../escape"}',
        '{"task": "a/b"}',
        '{"task": "two words"}',
        '{"task": 1}',
        '{"task": "."}',
        '{"task": "a\\\\b"}',
        '{"task": "$(touch-pwned)"}',
    ],
)
def test_invalid_routes_never_launch(entrypoint, tmp_path, body):
    (tmp_path / "configuration/task-routes.json").write_text(body)
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 2
    entrypoint.cli.main.assert_not_called()


def test_missing_routes_never_launch(entrypoint, tmp_path):
    with pytest.raises(SystemExit) as result:
        entrypoint.main(
            ["gello", "--task-routes", str(tmp_path / "absent.json")]
        )
    assert result.value.code == 2
    entrypoint.cli.main.assert_not_called()


@pytest.mark.parametrize(
    "camera,role", [("left", "third_left"), ("wrist", "wrist")]
)
def test_calibration_delegates_with_mounted_defaults(
    entrypoint, tmp_path, camera, role
):
    with mock.patch("subprocess.run", side_effect=AssertionError("nested run")):
        entrypoint.main(
            ["cali", f"--{camera}", "--validate-only", "--poses", "poses.json"]
        )
    args = entrypoint.commands.run.call_args.args[0]
    assert args.role == role and args.validate_only
    assert args.config == tmp_path / "configuration/teleop.ur.json"
    assert args.station == tmp_path / "configuration/recording.station.json"
    assert not args.operator_approved
    entrypoint.cli.main.assert_not_called()
