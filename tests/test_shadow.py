"""End-to-end software batches and truthful interrupt/cleanup reports."""

import json
from unittest import mock

import pytest

from ur12e_collection import shadow, storage, synthetic


def test_two_real_process_episodes_keep_one_rig(tmp_path):
    options = shadow.Options(
        "synthetic", tmp_path / "batch", "test", episodes=2, seconds=0.4
    )
    report = shadow.run(options)
    assert report["state"] == "completed" and report["simulated"]
    assert len(report["episodes"]) == 2
    clock_ids = set()
    for episode in report["episodes"]:
        result = storage.verify_episode(options.output / episode["episode"])
        assert result["counts"]["camera/frame_set"] > 0
        clock_ids.add(episode["recording"]["snapshot"]["clock_id"])
    assert len(clock_ids) == 1
    assert all(c["frames"] > 10 for c in report["cameras"].values())
    with pytest.raises(FileExistsError):
        shadow.run(options)


@pytest.mark.parametrize("failure", ["startup", "interrupt", "cleanup"])
def test_failed_batches_cannot_report_completion(tmp_path, failure):
    options = shadow.Options(
        "synthetic", tmp_path / "batch", "test", episodes=1, seconds=0.2
    )
    source = mock.MagicMock()
    source.observations = synthetic.observations(synthetic.configuration())
    source.clock_id = "test-clock"
    source.statistics.return_value = {}
    if failure == "startup":
        source.start.side_effect = TimeoutError("startup timed out")
    if failure == "cleanup":
        source.close.side_effect = RuntimeError("SDK stop failed")
    with (
        mock.patch.object(shadow.rig, "Rig", return_value=source),
        mock.patch.object(shadow, "_collect") as collect,
    ):
        if failure == "interrupt":
            collect.side_effect = KeyboardInterrupt
        with pytest.raises((TimeoutError, KeyboardInterrupt, RuntimeError)):
            shadow.run(options)
    source.close.assert_called_once()
    report = json.loads((options.output / "report.json").read_text())
    assert report["state"] == (
        "interrupted" if failure == "interrupt" else "failed"
    )
    assert report["episodes"] == []


def test_real_interrupt_closes_active_batch(tmp_path):
    import signal
    import subprocess
    import sys
    import time

    output = tmp_path / "interrupt"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ur12e_collection",
            "shadow",
            "--backend",
            "synthetic",
            "--output",
            str(output),
            "--revision",
            "test",
            "--episodes",
            "2",
            "--seconds",
            "40",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if (output / "episode-0000.partial" / "episode.mcap").exists():
                break
            assert process.poll() is None
            time.sleep(0.02)
        else:
            pytest.fail("shadow did not begin recording")
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 130, stdout + stderr
        report = json.loads((output / "report.json").read_text())
        assert report["state"] == "interrupted"
        assert report["episodes"] == []
        assert not (output / "episode-0000").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
