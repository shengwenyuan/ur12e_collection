"""Independent verification returns real results and obeys owner cancellation."""

import multiprocessing

import pytest

from ur12e_collection import archive, matching, verification


def test_process_verifies_closed_file_and_rejects_corruption(
    tmp_path, snapshot, group_factory
):
    path = tmp_path / "episode.mcap"
    with path.open("wb") as stream:
        writer = archive.ArchiveWriter(stream, snapshot, True, 20)
        writer.group(group_factory())
        writer.finish()
    abort = multiprocessing.get_context("spawn").Event()
    checker = verification.Verifier(abort)
    try:
        result = checker.verify(path, snapshot, True, matching.MatchConfig())
        assert result["counts"]["camera/frame_set"] == 1
        assert result["all_depth_hashes_verified"]
        path.write_bytes(b"invalid MCAP")
        with pytest.raises(RuntimeError, match="verification failed"):
            checker.verify(path, snapshot, True, matching.MatchConfig())
        abort.set()
        with pytest.raises(RuntimeError, match="aborted"):
            checker.verify(path, snapshot, True, matching.MatchConfig())
    finally:
        checker.close()
    assert not checker.process.is_alive()
