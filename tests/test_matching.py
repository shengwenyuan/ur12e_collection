"""M08 timing, bounded buffering, provenance, and nearest-frame behavior."""

import dataclasses

import pytest

from ur12e_collection import matching

MS = 1_000_000


def test_nearest_tie_prefers_earlier_and_preserves_provenance(frame_factory):
    matcher = matching.Matcher("fixture-unix")
    matcher.push(frame_factory("wrist", 20 * MS), 20 * MS)
    for role in ("third_left", "third_right"):
        matcher.push(frame_factory(role, 10 * MS, receipt=20 * MS), 20 * MS)
    matcher.push(frame_factory("third_left", 30 * MS, 1), 30 * MS)
    result = matcher.push(frame_factory("third_right", 30 * MS, 1), 30 * MS)
    assert len(result) == 1 and result[0].accepted
    assert [f.color.sequence for f in result[0].members] == [0, 0, 0]
    assert result[0].metadata()["skews_ns"]["third_left"] == -10 * MS
    assert result[0].members[1].color.time.source_clock == "fixture-camera"


@pytest.mark.parametrize(
    "skew,accepted", [(16_700_000, True), (16_700_001, False)]
)
def test_inclusive_skew_boundary(frame_factory, skew, accepted):
    matcher = matching.Matcher("fixture-unix")
    matcher.push(frame_factory("wrist", 0), 0)
    matcher.push(frame_factory("third_left", skew), skew)
    result = matcher.push(frame_factory("third_right", skew), skew)
    assert result[0].accepted is accepted


def test_late_arrival_cannot_recover_expired_anchor(frame_factory):
    matcher = matching.Matcher("fixture-unix")
    matcher.push(frame_factory("wrist", 0), 0)
    matcher.push(frame_factory("third_left", 0), 0)
    assert not matcher.advance(49 * MS)
    result = matcher.push(
        frame_factory("third_right", 0, receipt=51 * MS), 51 * MS
    )
    assert [r.reason for r in result] == ["missing_view"]


def test_depth_is_not_reused_even_with_new_color(frame_factory):
    matcher = matching.Matcher("fixture-unix")
    results = []
    for index in range(2):
        for role in ("wrist", "third_left", "third_right"):
            results += matcher.push(
                frame_factory(role, index * 33 * MS, index, depth_index=0),
                index * 33 * MS,
            )
    assert results[0].accepted
    assert results[1].reason == "frame_reuse"


def test_wrist_overflow_and_finish_report_every_anchor(frame_factory):
    matcher = matching.Matcher("fixture-unix", matching.MatchConfig(capacity=2))
    results = []
    for index in range(3):
        results += matcher.push(
            frame_factory("wrist", index * MS, index), index * MS
        )
    results += matcher.finish(3 * MS)
    assert [r.reason for r in results] == [
        "overflow",
        "missing_view",
        "missing_view",
    ]
    assert not matcher.finish(4 * MS)


@pytest.mark.parametrize(
    "change", ["clock", "counter", "generation", "identity"]
)
def test_discontinuity_requires_explicit_new_generation(frame_factory, change):
    matcher = matching.Matcher("fixture-unix")
    matcher.push(frame_factory("wrist", 0), 0)
    frame = frame_factory("wrist", MS, 1)
    if change == "clock":
        frame = dataclasses.replace(frame, clock_id="unrelated-hardware-clock")
    elif change == "counter":
        frame = frame_factory("wrist", MS, 0)
    elif change == "generation":
        frame = dataclasses.replace(frame, generation=1)
    else:
        frame = dataclasses.replace(
            frame,
            color=dataclasses.replace(frame.color, source_id="other"),
            depth=dataclasses.replace(frame.depth, source_id="other"),
        )
    with pytest.raises(matching.SourceFault) as caught:
        matcher.push(frame, MS)
    assert caught.value.generation == 0
    assert [r.reason for r in caught.value.rejections] == ["source_fault"]
    with pytest.raises(matching.SourceFault) as blocked:
        matcher.push(frame_factory("third_left", MS), MS)
    assert not blocked.value.rejections
    with pytest.raises(ValueError):
        matcher.reset(0)
    matcher.reset(1)
    assert (
        matcher.push(frame_factory("wrist", 2 * MS, generation=1), 2 * MS) == []
    )


def test_unrelated_camera_identity_and_host_clock_are_rejected(frame_factory):
    matcher = matching.Matcher("fixture-unix")
    matcher.push(frame_factory("wrist", MS), MS)
    with pytest.raises(ValueError):
        matcher.advance(0)
    with pytest.raises(ValueError):
        matcher.push(frame_factory("third_left", 2 * MS), MS)
    frame = dataclasses.replace(frame_factory("wrist", MS), role="third_left")
    with pytest.raises(matching.SourceFault) as caught:
        matcher.push(frame, MS)
    assert caught.value.rejections[0].reason == "source_fault"


@pytest.mark.parametrize("pending", [False, True])
def test_source_fault_always_signals_and_reset_discards_old_frames(
    frame_factory, pending
):
    matcher = matching.Matcher("fixture-unix")
    matcher.push(frame_factory("third_left", 0), 0)
    if pending:
        matcher.push(frame_factory("wrist", 0), 0)
    with pytest.raises(matching.SourceFault) as caught:
        matcher.push(frame_factory("third_left", MS, 0), MS)
    assert caught.value.generation == 0
    assert len(caught.value.rejections) == int(pending)
    assert all(r.reason == "source_fault" for r in caught.value.rejections)
    assert not matcher.advance(2 * MS)
    assert not matcher.finish(2 * MS)
    assert matcher.counters["source_fault_events"] == 1
    matcher.reset(1)
    # A new wrist cannot reuse the old third-view buffers.
    matcher.push(frame_factory("wrist", 3 * MS, generation=1), 3 * MS)
    matcher.push(frame_factory("third_right", 3 * MS, generation=1), 3 * MS)
    assert not matcher.advance(3 * MS)
    result = matcher.push(
        frame_factory("third_left", 3 * MS, generation=1), 3 * MS
    )
    assert len(result) == 1 and result[0].accepted
    assert all(f.generation == 1 for f in result[0].members)
