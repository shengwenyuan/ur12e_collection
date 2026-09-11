"""Replay timing, provenance, loop boundaries and real archive verification."""

import importlib.util
import json
import pathlib
import sys
from unittest import mock

import pytest

from ur12e_collection import codecs, contracts


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, pathlib.Path(__file__).parent / "replay" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FEED = load("feed")


@pytest.fixture
def cache_path(tmp_path, group_factory, snapshot):
    path = tmp_path / "cache"
    path.mkdir()
    groups = [group_factory(i) for i in range(2)]
    metadata = []
    for group in groups:
        value = group.metadata()
        value["depth_sha256"] = {
            f.role: codecs.depth_digest(f.payload.depth) for f in group.members
        }
        metadata.append(value)
    for index, role in enumerate(contracts.CAMERA_ROLES):
        snapshot["cameras"][role]["source_id"] = role
        for kind, field in (("rgb", "rgb"), ("depth", "depth")):
            (path / f"{role}.{kind}.raw").write_bytes(
                b"".join(
                    getattr(g.members[index].payload, field).tobytes()
                    for g in groups
                )
            )
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "origin": "replay",
                "groups": metadata,
                "frames_per_role": 2,
                "source_metadata": {"snapshot": snapshot},
            }
        )
    )
    return path


def test_loop_preserves_original_time_depth_and_explicit_replay_identity(
    cache_path,
):
    cache = FEED.Cache(cache_path)
    try:
        first = cache.frame("wrist", 0, "epoch", 100, 1_800_000_000_000_000_000)
        loop = cache.frame("wrist", 2, "epoch", 200, 1_800_000_000_000_000_000)
        assert first.color.simulated and first.color.source_id == "replay-wrist"
        assert first.color.time.source_clock.startswith("replay-original:")
        assert first.color.time.source_ns == loop.color.time.source_ns
        assert loop.color.sequence > first.color.sequence
        assert loop.timestamp_ns - first.timestamp_ns == cache.period_ns
        assert cache.due("wrist", 2) == cache.period_ns
        assert codecs.depth_digest(first.payload.depth) == codecs.depth_digest(
            loop.payload.depth
        )
        context = cache.snapshot("epoch", "fixture")
        assert cache.identity in context["task"]
        assert context["simulated"] and "feedback" not in context
        assert context["station"]["motion_accepted"] is False
        assert context["station"]["ur"]["host"] != "10.18.1.106"
    finally:
        cache.close()


def test_corrupted_cached_depth_and_wrong_file_size_fail(cache_path):
    path = cache_path / "wrist.depth.raw"
    with path.open("r+b") as stream:
        stream.write(b"\xff\xff")
    cache = FEED.Cache(cache_path)
    try:
        with pytest.raises(ValueError, match="hash mismatch"):
            cache.frame("wrist", 0, "epoch", 1, 100)
    finally:
        cache.close()
    path.write_bytes(b"truncated")
    with pytest.raises(ValueError, match="size"):
        FEED.Cache(cache_path)


def test_three_producer_replay_uses_real_writer_without_hardware(
    cache_path, tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "feed", FEED)
    runner = load("run")
    with mock.patch("socket.socket", side_effect=AssertionError("no network")):
        result = runner.run(cache_path, tmp_path / "run", 0.25, "fixture")
    assert result["state"] == "completed", result
    assert result["result"]["matching"]["accepted"] >= 5
    assert all(
        s["queue_peak"] <= 8 and not s["error"]
        for s in result["source"].values()
    )
    assert (
        result["result"]["recording"]["verification"]["counts"][
            "camera/frame_set"
        ]
        >= 5
    )
    assert result["physical_leader_in_archive"] is False
