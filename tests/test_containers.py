"""Opt-in M01 container checks; run with UR12E_TEST_IMAGE set explicitly."""

import json
import os
import subprocess

import pytest

IMAGE = os.environ.get("UR12E_TEST_IMAGE")
pytestmark = pytest.mark.skipif(not IMAGE, reason="container checks are opt-in")


def _run(config, data, *arguments, readonly=False):
    mounts = [
        "--mount",
        f"type=bind,src={config},dst=/config"
        + (",readonly" if readonly else ""),
        "--mount",
        f"type=bind,src={data},dst=/data",
    ]
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            *mounts,
            IMAGE,
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_replacement_preserves_mounts(tmp_path):
    """Distinct container instances share the same unchanged station and data."""
    config, data = tmp_path / "config", tmp_path / "data"
    config.mkdir()
    data.mkdir()
    fixture = data / "episode-fixture.bin"
    fixture.write_bytes(bytes(range(256)))
    first = _run(
        config,
        data,
        "station",
        "initialize",
        "--output",
        "/config/station.json",
    )
    assert first.returncode == 0, first.stderr
    before = (config / "station.json").read_bytes()
    second = _run(
        config, data, "doctor", "--format", "json", "--require-mounts"
    )
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["software_ready"]
    assert (config / "station.json").read_bytes() == before
    assert fixture.read_bytes() == bytes(range(256))


def test_readonly_mount_fails_without_changes(tmp_path):
    """A read-only configuration bind fails required mount checks honestly."""
    config, data = tmp_path / "config", tmp_path / "data"
    config.mkdir()
    data.mkdir()
    fixture = config / "preserve.txt"
    fixture.write_text("unchanged")
    result = _run(
        config,
        data,
        "doctor",
        "--format",
        "json",
        "--require-mounts",
        readonly=True,
    )
    assert result.returncode == 1, result.stderr
    assert (
        json.loads(result.stdout)["mounts"]["config"]["state"] == "unavailable"
    )
    assert fixture.read_text() == "unchanged"
