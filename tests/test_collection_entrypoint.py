"""Daily collection commands reuse the hardware launcher without executing it."""

import importlib.util
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
    assert args.record_output == expected.expanduser().resolve()
    assert args.image == "ur12e-collection:current"
    assert args.operator_approved and not args.preflight
    assert args.task == "gello_collection"
    assert not args.record_output.exists()


@pytest.mark.parametrize(
    "argv", [["--help"], ["gello", "--help"], ["dagger"], []]
)
def test_help_and_unknown_modes_never_launch(entrypoint, argv):
    with pytest.raises(SystemExit) as result:
        entrypoint.main(argv)
    assert result.value.code == (0 if "--help" in argv else 2)
    entrypoint.teleop.main.assert_not_called()


def test_missing_station_never_launches(entrypoint, capsys):
    (entrypoint.teleop.ROOT / "config/local/recording.station.json").unlink()
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 2
    assert "missing station configuration" in capsys.readouterr().err
    entrypoint.teleop.main.assert_not_called()


def test_launcher_exit_is_preserved(entrypoint):
    entrypoint.teleop.main.side_effect = SystemExit(7)
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["gello"])
    assert result.value.code == 7
