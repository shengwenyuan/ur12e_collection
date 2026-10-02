"""Daily collection commands reuse the hardware launcher without executing it."""

import importlib.util
import json
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def entrypoint(tmp_path, monkeypatch):
    scripts = Path(__file__).parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "collection_entrypoint", scripts / "ur12e.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "deployment"
    (root / "config/local").mkdir(parents=True)
    (root / "config/teleop.ur.json").write_text("{}")
    (root / "config/task-routes.json").write_text(
        json.dumps({"Pick up the red block.": "red-block"})
    )
    monkeypatch.setattr("builtins.input", lambda _: "1")
    (root / "config/local/recording.station.json").write_text("{}")
    monkeypatch.setattr(module.teleop, "ROOT", root)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "operator"))
    monkeypatch.setattr(module.teleop, "main", mock.Mock())
    return module


@pytest.mark.parametrize("output", [None, "new captures", "~/custom"])
def test_recording_arguments_resolve_independently_of_deployment(
    entrypoint, output
):
    argv = ["gello"] + (["--output", output] if output else [])
    entrypoint.main(argv)
    command = entrypoint.teleop.main.call_args.args[0]
    args = entrypoint.teleop.arguments(command)[0]
    root = entrypoint.teleop.ROOT
    assert args.config == root / "config/teleop.ur.json"
    assert args.record_station == root / "config/local/recording.station.json"
    expected = Path(output) if output else Path.home() / "ur12e-data"
    assert args.record_output == expected.expanduser().resolve() / "red-block"
    assert args.image == "ur12e-collection:current"
    assert args.operator_approved and not args.preflight
    assert args.task == "Pick up the red block."
    assert not args.record_output.exists()


@pytest.mark.parametrize(
    "argv", [["--help"], ["gello", "--help"], ["dagger"], []]
)
def test_help_and_unknown_modes_never_launch(entrypoint, argv):
    with pytest.raises(SystemExit) as result:
        entrypoint.main(argv)
    assert result.value.code == (0 if "--help" in argv else 2)
    entrypoint.teleop.main.assert_not_called()


def test_calibration_preview_on_pc_uses_offline_image(entrypoint, monkeypatch):
    root = entrypoint.teleop.ROOT
    route = root / "left.json"
    route.write_text("{}")
    monkeypatch.setattr(entrypoint.cali.sys, "platform", "linux")
    factory = mock.Mock(return_value=(["docker", "run"], "pinned-image"))
    monkeypatch.setattr(entrypoint.teleop, "container_command", factory)
    launch = mock.Mock(return_value=mock.Mock(returncode=0))
    monkeypatch.setattr(entrypoint.cali.subprocess, "run", launch)
    check = mock.Mock(side_effect=AssertionError("no network probe"))
    monkeypatch.setattr(entrypoint.cali.network, "check", check)
    assert (
        entrypoint.main(
            ["cali", "--left", "--poses", str(route), "--validate-only"]
        )
        == 0
    )
    factory.assert_called_once_with(
        "ur12e-collection:current", "2g", physical=False, interactive=False
    )
    command = launch.call_args.args[0]
    assert "--device" not in command and "--operator-approved" not in command
    assert f"{route}:{route}:ro" in command
    assert "--validate-only" in command
    check.assert_not_called()


def test_calibration_replay_requires_operator_before_network(
    entrypoint, monkeypatch
):
    monkeypatch.setattr(entrypoint.cali.sys, "platform", "linux")
    launch = mock.Mock()
    monkeypatch.setattr(entrypoint.cali.subprocess, "run", launch)
    with pytest.raises(SystemExit) as error:
        entrypoint.main(["cali", "--left", "--replay"])
    assert error.value.code == 2
    launch.assert_not_called()


def test_missing_station_never_launches(entrypoint, capsys):
    (entrypoint.teleop.ROOT / "config/local/recording.station.json").unlink()
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 2
    assert "missing station configuration" in capsys.readouterr().err
    entrypoint.teleop.main.assert_not_called()


def test_station_local_profile_overrides_repository_default(entrypoint):
    configuration = entrypoint.teleop.ROOT / "config/local/teleop.ur.json"
    configuration.write_text("{}")
    entrypoint.main(["gello"])
    command = entrypoint.teleop.main.call_args.args[0]
    args = entrypoint.teleop.arguments(command)[0]
    assert args.config == configuration
    assert args.record_station.parent == configuration.parent


def test_launcher_exit_is_preserved(entrypoint):
    entrypoint.teleop.main.side_effect = SystemExit(7)
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 7


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
    command = entrypoint.teleop.main.call_args.args[0]
    args = entrypoint.teleop.arguments(command)[0]
    assert args.task == description
    assert args.record_output == Path.home() / "ur12e-data/red-box"
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
    entrypoint.teleop.main.assert_not_called()


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
def test_invalid_routes_never_launch(entrypoint, body):
    path = entrypoint.teleop.ROOT / "config/task-routes.json"
    path.write_text(body)
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 2
    entrypoint.teleop.main.assert_not_called()


def test_missing_routes_never_launch(entrypoint):
    (entrypoint.teleop.ROOT / "config/task-routes.json").unlink()
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 2
    entrypoint.teleop.main.assert_not_called()
