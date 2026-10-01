"""The host terminal exposes persistent mounts and a shared controller lease."""

import argparse
import importlib.util
import json
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def terminal(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "collection_terminal", Path(__file__).parents[1] / "scripts/enter.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = tmp_path / "configuration"
    config.mkdir()
    serial = f"offline-terminal-{tmp_path.name}"
    profile = {
        "follower": {"backend": "ur", "serial": serial},
        "leader": {"device": str(tmp_path / "leader")},
    }
    (config / "teleop.ur.json").write_text(json.dumps(profile))
    args = argparse.Namespace(
        config_dir=config,
        data_dir=tmp_path / "data",
        evidence_dir=tmp_path / "evidence",
        image="current",
        name="test-terminal",
    )
    monkeypatch.setattr(
        module.containers,
        "container_command",
        mock.Mock(return_value=(["docker", "run"], "sha256:pinned")),
    )
    monkeypatch.setattr(
        module.containers, "camera_devices", mock.Mock(return_value=[])
    )
    yield module, args, profile
    (Path("/tmp") / f"ur12e-controller-{serial}.lock").unlink(missing_ok=True)


@pytest.mark.parametrize("connected", [False, True])
def test_terminal_mounts_without_starting_a_session(terminal, connected):
    module, args, profile = terminal
    leader = Path(profile["leader"]["device"])
    if connected:
        leader.touch()
    command = module.shell_command(args)
    assert command[-5:] == [
        "/entrypoint.sh",
        "sha256:pinned",
        "bash",
        "--noprofile",
        "--norc",
    ]
    assert f"{args.config_dir}:/config:ro" in command
    assert f"{args.data_dir}:/data:rw" in command
    assert f"{args.evidence_dir}:/evidence:rw" in command
    lease = (
        Path("/tmp") / f"ur12e-controller-{profile['follower']['serial']}.lock"
    )
    inode = lease.stat().st_ino
    assert f"{lease}:/run/ur12e-controller.lock:rw" in command
    assert "UR12E_LEASE=/run/ur12e-controller.lock" in command
    assert "UR12E_CONFIG_DIR=/config" in command
    assert "UR12E_DATA_DIR=/data" in command
    assert "--operator-approved" not in command
    assert "--privileged" not in command
    assert not any("docker.sock" in arg for arg in command)
    assert args.data_dir.is_dir() and args.evidence_dir.is_dir()
    module.containers.container_command.assert_called_once_with(
        "current", "8g", physical=True
    )
    if connected:
        assert f"{leader}:{leader}:rw" in command
        assert str(leader.stat().st_gid) in command
    else:
        assert not any(str(leader) in arg for arg in command)
    module.shell_command(args)
    assert lease.stat().st_ino == inode


def test_nonphysical_profile_rejected_before_docker(terminal):
    module, args, profile = terminal
    profile["follower"]["backend"] = "isaac"
    (args.config_dir / "teleop.ur.json").write_text(json.dumps(profile))
    with pytest.raises(ValueError, match="physical UR profile"):
        module.shell_command(args)
    module.containers.container_command.assert_not_called()


def test_linux_main_propagates_shell_exit(terminal, monkeypatch):
    module, args, _ = terminal
    monkeypatch.setattr(module.sys, "platform", "linux")
    with mock.patch.object(
        module.subprocess, "run", return_value=mock.Mock(returncode=9)
    ) as run:
        assert (
            module.main(
                [
                    "--config-dir",
                    str(args.config_dir),
                    "--data-dir",
                    str(args.data_dir),
                    "--evidence-dir",
                    str(args.evidence_dir),
                ]
            )
            == 9
        )
    assert run.call_args.kwargs == {"check": False}


def test_help_never_inspects_images(terminal):
    module, _, _ = terminal
    with pytest.raises(SystemExit) as result:
        module.main(["--help"])
    assert result.value.code == 0
    module.containers.container_command.assert_not_called()
