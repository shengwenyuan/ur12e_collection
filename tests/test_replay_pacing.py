"""Image workload pacing never changes original acquisition evidence."""

import threading
from unittest import mock

import pytest

from replay import quality, rig


@pytest.mark.parametrize("pacing", ["original", "uniform30"])
def test_replay_schedule_keeps_source_identity_and_depth_offset(
    frame_factory, pacing
):
    source = frame_factory("third_left", 12_000_000, index=71)
    cache = mock.Mock()
    cache.frame.return_value = source
    cache.due.return_value = 59_000_000
    cache.snapshot.return_value = {"cameras": {}}
    with mock.patch.object(rig, "Cache", return_value=cache):
        owner = rig.Rig("unused", {}, {}, threading.Event(), pacing=pacing)
    owner.started, owner.offset = 100_000_000, 1_700_000_000_000_000_000
    due, result = owner.scheduled("third_left", 3)
    assert result.color == source.color and result.depth == source.depth
    assert result.payload is source.payload
    assert (
        result.depth_timestamp_ns - result.timestamp_ns
        == source.depth_timestamp_ns - source.timestamp_ns
    )
    if pacing == "original":
        assert due == 159_000_000 and result is source
    else:
        assert due == 204_000_000
        assert result.timestamp_ns == due + owner.offset
        later, _ = owner.scheduled("third_left", 33)
        assert later - due == 1_000_000_000
    owner.close()


def test_bad_pacing_is_rejected_before_reading_cache():
    with mock.patch.object(rig, "Cache") as cache:
        with pytest.raises(ValueError, match="pacing"):
            rig.Rig("unused", {}, {}, threading.Event(), pacing="invented")
        cache.assert_not_called()


def test_rgb_quality_keeps_exact_matches_separate_from_finite_psnr():
    result = quality.summarize([None, 40.0, 50.0])
    assert result == {
        "frames": 3,
        "exact_frames": 1,
        "mean_finite_psnr_db": 45.0,
        "minimum_psnr_db": 40.0,
    }
