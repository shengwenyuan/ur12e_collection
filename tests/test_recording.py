"""Receipt watermarks and verified stops guard independent recording commits."""

import dataclasses
import multiprocessing
import queue
import threading
from types import SimpleNamespace
from unittest import mock
import time

import pytest

from ur12e_collection import matching, recording, session, storage
from ur12e_collection.control.records import Records
from test_control_records import samples


class Source:
    def __init__(self, frames=()):
        self.frames = list(frames)

    def statistics(self):
        return {}

    def read(self):
        result, self.frames = self.frames, []
        return result


def test_busy_heartbeat_lock_does_not_block_or_refresh_control(monkeypatch):
    owner = recording.Recorder.__new__(recording.Recorder)
    owner.process = mock.Mock()
    owner.process.is_alive.return_value = True
    owner.replies = queue.Queue()
    owner.commands = queue.Queue()
    owner.pulse = multiprocessing.get_context("spawn").Value("q", 0)
    owner.ready = True
    now = time.monotonic_ns()
    owner.last_reply = owner.last_heartbeat = now
    held, release = threading.Event(), threading.Event()

    def hold_lock():
        with owner.pulse.get_lock():
            owner.pulse.get_obj().value = now + 10
            held.set()
            release.wait(1)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    try:
        assert held.wait(1)
        started = time.monotonic()
        assert owner.poll() == []
        assert time.monotonic() - started < 0.05
        assert owner.last_reply == now
        monkeypatch.setattr(
            recording.time,
            "monotonic_ns",
            lambda: now + recording.HEARTBEAT_NS + 1,
        )
        with pytest.raises(RuntimeError, match="status is stale"):
            owner.poll()
    finally:
        release.set()
        thread.join(2)


def test_exited_recorder_is_rejected_before_receiving_messages():
    owner = recording.Recorder.__new__(recording.Recorder)
    owner.process = mock.Mock()
    owner.process.is_alive.return_value = False
    owner.replies = mock.Mock()
    with pytest.raises(RuntimeError, match="process exited"):
        owner.poll()
    owner.replies.get_nowait.assert_not_called()


def test_watermark_excludes_post_stop_frames_and_waits_for_standstill(
    tmp_path, controlled, group_factory
):
    owner = session.Session(controlled, matching.MatchConfig())
    source = Source([*group_factory().members, *group_factory(1).members])
    capture = recording._Capture(source, owner)
    data = samples(controlled)
    capture.message("prepare", str(tmp_path / "episode"))
    capture.message("begin", (0, data[0]))
    capture.step(4_000_000)
    assert not owner.matcher.counters
    capture.message("samples", (4_000_000, data[1:-1]))
    capture.step(5_000_000)
    release = dataclasses.replace(
        data[-1],
        provenance=dataclasses.replace(
            data[-1].provenance,
            time=dataclasses.replace(
                data[-1].provenance.time,
                source_ns=20_000_000,
                received_monotonic_ns=20_000_000,
            ),
        ),
    )
    capture.message("stop", (20_000_000, release))
    capture.step(100_000_000)
    assert owner.state == "recording"
    assert not (tmp_path / "episode").exists()
    capture.message("settled", None)
    report = capture.step(100_000_001)
    deadline = time.monotonic() + 3
    while report is None and time.monotonic() < deadline:
        report = owner.poll()
        time.sleep(0.005)
    assert report["matching"]["accepted"] == 1
    assert report["stop_receipt_ns"] == 20_000_000
    assert (
        storage.verify_episode(tmp_path / "episode")["counts"][
            "camera/frame_set"
        ]
        == 1
    )
    owner.close()


def test_prepared_writer_never_admits_images_before_begin(
    tmp_path, controlled, group_factory
):
    owner = session.Session(controlled, matching.MatchConfig())
    owner.prepare(tmp_path / "prepared")
    for frame in group_factory().members:
        owner.submit(frame, 5_000_000)
    assert not owner.matcher.counters
    owner.close()
    assert not (tmp_path / "prepared").exists()


def test_stop_cannot_precede_admitted_watermark(tmp_path, controlled):
    owner = session.Session(controlled, matching.MatchConfig())
    capture = recording._Capture(Source(), owner)
    factory = Records(controlled["control"], simulated=True)
    capture.message("prepare", str(tmp_path / "cutoff"))
    capture.message("begin", (100, factory.authority("acquired", "space", 100)))
    with pytest.raises(RuntimeError, match="watermark"):
        capture.message(
            "stop", (99, factory.authority("released", "space", 99))
        )
    owner.close()


@pytest.mark.parametrize("cancelled", [True, False])
def test_camera_exit_after_cancel_cleans_partial_without_false_fault(
    tmp_path, controlled, monkeypatch, capsys, cancelled
):
    abort = threading.Event()
    replies = queue.Queue()
    replies.cancel_join_thread = lambda: None
    source = mock.Mock()
    source.clock_id = controlled["clock_id"]
    source.observations = {}
    monkeypatch.setattr(recording.rig, "Rig", lambda *a, **k: source)
    monkeypatch.setattr(recording.snapshots, "build", lambda *a: controlled)
    verifier = mock.Mock()
    monkeypatch.setattr(recording.verification, "Verifier", lambda *a: verifier)
    destination = tmp_path / "interrupted"

    def interrupted(capture, _channels):
        capture.owner.prepare(destination)
        if cancelled:
            abort.set()
        raise RuntimeError("camera worker exited: wrist")

    monkeypatch.setattr(recording, "_run", interrupted)
    recording._worker(
        controlled["station"],
        controlled,
        (queue.Queue(), replies, abort, SimpleNamespace(value=0), {}),
    )
    assert abort.is_set()
    assert not destination.exists()
    assert destination.with_suffix(".partial").is_dir()
    source.close.assert_called_once()
    verifier.close.assert_called_once()
    assert replies.get_nowait()[0] == "ready"
    output = capsys.readouterr().out
    if cancelled:
        assert output == ""
        assert replies.empty()
    else:
        assert "recorder worker failed" in output
        assert replies.get_nowait() == ("error", "camera worker exited: wrist")


def test_three_controlled_episodes_reuse_capture_and_verify_gripper_stream(
    tmp_path, controlled, group_factory, frame_factory
):
    """Exercise real codecs, writer, verifier and record clocks across rotation."""
    from ur12e_collection import snapshots
    from ur12e_collection.control import model
    from test_collection import hande

    controlled["control"].update(
        hande="urcap", hande_id="test-hande", writer_feedback_capacity=128
    )
    controlled = snapshots.copy(controlled)
    owner = session.Session.from_snapshot(controlled)
    source = Source()
    capture = recording._Capture(source, owner)
    try:
        for index in range(3):
            start = index * 1_000_000_000
            path = tmp_path / f"episode-{index}"
            factory = Records(controlled["control"], simulated=True)
            capture.message("prepare", str(path))
            capture.message(
                "begin", (start, factory.authority("acquired", "space", start))
            )
            original = group_factory(index)
            source.frames = [
                dataclasses.replace(
                    frame_factory(f.role, start + 1_000_000, index),
                    payload=f.payload,
                )
                for f in original.members
            ]
            data = []
            # 120-Hz commands, independent 125-Hz UR and 10-Hz raw Hand-E.
            for seq in range(24):
                stamp = start + 2_000_000 + seq * 8_333_333
                target = model.Target((0.0,) * 6, seq, stamp, "simulation-wave")
                data.extend(
                    (factory.intent(target), factory.sent(target, stamp + 1))
                )
            for seq in range(25):
                stamp = start + 3_000_000 + seq * 8_000_000
                state = model.State(
                    (0.0,) * 6,
                    (0.0,) * 6,
                    stamp / 1e9,
                    stamp,
                    currents=(0.0,) * 6,
                    tcp=(0.0,) * 6,
                )
                data.extend(factory.feedback(state))
            for seq in range(2):
                data.extend(
                    factory.observed(
                        hande(start + 4_000_000 + seq * 100_000_000, seq)
                    )
                )
            capture.message("samples", (start + 199_000_000, tuple(data)))
            capture.step(start + 5_000_000)
            cutoff = start + 200_000_000
            capture.message(
                "stop", (cutoff, factory.authority("released", "space", cutoff))
            )
            capture.message("settled", None)
            report = capture.step(cutoff + 100_000_000)
            deadline = time.monotonic() + 5
            while report is None and time.monotonic() < deadline:
                report = owner.poll()
                time.sleep(0.005)
            assert report is not None
            counts = storage.verify_episode(path)["counts"]
            assert counts["leader/state"] == 24
            assert counts["follower/state"] == 52
            assert counts["camera/frame_set"] == 1
            assert counts["control/command"] == 24
            assert capture.source is source
    finally:
        owner.close()
