"""Episode lifecycle boundaries and asynchronous finalization ownership."""

import threading
import time
from unittest import mock

import pytest

from ur12e_collection import archive, matching, session, storage


def _submit(owner, group):
    for frame in group.members:
        owner.submit(frame, frame.color.time.received_monotonic_ns)


def test_finalize_is_nonblocking_and_cannot_leak_next_episode(
    tmp_path, snapshot, group_factory
):
    owner = session.Session(snapshot, matching.MatchConfig())
    entered, release = threading.Event(), threading.Event()
    original = archive.verify_mcap

    def delayed(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    owner.start(tmp_path / "first", 1_000_000)
    _submit(owner, group_factory())
    with mock.patch.object(archive, "verify_mcap", delayed):
        owner.stop(2_000_000)
        try:
            assert entered.wait(2)
            assert owner.state == "finalizing" and owner.poll() is None
            owner.submit(group_factory(1).anchor, 40_000_000)
            with pytest.raises(RuntimeError, match="idle"):
                owner.start(tmp_path / "too-early", 40_000_000)
        finally:
            release.set()
        deadline = time.monotonic() + 3
        result = None
        while result is None and time.monotonic() < deadline:
            result = owner.poll()
            time.sleep(0.005)
    assert (
        result["recording"]["verification"]["counts"]["camera/frame_set"] == 1
    )
    owner.start(tmp_path / "second", 40_000_000)
    _submit(owner, group_factory())  # Old receipts cannot enter this episode.
    assert not owner.matcher.counters
    owner.abort()
    owner.close()
    assert not (tmp_path / "second").exists()
    assert (tmp_path / "first").exists()


def test_matching_fault_aborts_current_episode(
    tmp_path, snapshot, group_factory
):
    owner = session.Session(snapshot, matching.MatchConfig())
    owner.start(tmp_path / "fault", 0)
    group = group_factory()
    _submit(owner, group)
    with pytest.raises(matching.SourceFault):
        owner.submit(group.anchor, 2_000_000)
    owner.close()
    assert not (tmp_path / "fault").exists()


def test_capture_cutoff_is_distinct_from_finalization_request(
    tmp_path, snapshot, group_factory
):
    owner = session.Session(snapshot, matching.MatchConfig())
    owner.start(tmp_path / "drained", 1_000_000)
    _submit(owner, group_factory())
    with pytest.raises(ValueError, match="cutoff"):
        owner.stop(3_000_000, cutoff_ns=4_000_000)
    owner.stop(3_000_000, cutoff_ns=2_000_000)
    assert owner.writer.wait_closed()
    deadline = time.monotonic() + 2
    result = None
    while result is None and time.monotonic() < deadline:
        result = owner.poll()
        time.sleep(0.001)
    assert result["stop_receipt_ns"] == 2_000_000
    assert result["finalize_requested_ns"] == 3_000_000
    assert result["matching"]["accepted"] == 1
    owner.close()


def test_frame_beyond_drain_budget_cannot_silently_complete(
    tmp_path, snapshot, group_factory
):
    owner = session.Session(snapshot, matching.MatchConfig())
    entered, release = threading.Event(), threading.Event()
    original = archive.verify_mcap

    def delayed(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    owner.start(tmp_path / "late-tail", 0)
    _submit(owner, group_factory())
    with mock.patch.object(archive, "verify_mcap", delayed):
        owner.stop(100_000_000, cutoff_ns=40_000_000)
        try:
            assert entered.wait(2)
            with pytest.raises(storage.RecordingError, match="capture drain"):
                owner.submit(group_factory(1).anchor, 101_000_000)
        finally:
            release.set()
        owner.close()
    assert not (tmp_path / "late-tail").exists()


def test_async_writer_failure_is_observable(tmp_path, snapshot, group_factory):
    owner = session.Session(snapshot, matching.MatchConfig())
    with mock.patch.object(
        archive.ArchiveWriter, "group", side_effect=OSError("disk fault")
    ):
        owner.start(tmp_path / "failed", 0)
        _submit(owner, group_factory())
        assert owner.writer.wait_closed()
        with pytest.raises(storage.RecordingError, match="disk fault"):
            owner.poll()
    owner.close()
