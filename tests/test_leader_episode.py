"""Relative intent does not accumulate drift, change its anchor or hide faults."""

import dataclasses
import math

import pytest

from ur12e_collection.control import model
from ur12e_collection.leader import episode, mapping

HOME = (0, -math.pi / 2, -math.pi / 2, -math.pi / 2, math.pi / 2, 0)


def calibration():
    return mapping.Calibration(
        HOME,
        tuple(
            mapping.Joint(2048, s, 1024, 3072) for s in (1, -1, 1, -1, 1, -1)
        ),
        3200,
        3800,
        "test fixture",
        "a" * 64,
    )


def sample(seq, raw=2200, epoch="serial-session-1"):
    return episode.Sample(
        epoch,
        seq,
        seq * 20_000_000,
        seq * 20_000_000 + 1_000_000,
        (raw,) * 6 + (3200,),
    )


def start(raw=2200, **options):
    limits = options.get("limits", model.Limits((-6.0,) * 6, (6.0,) * 6, HOME))
    follower = options.get(
        "follower", model.State(HOME, (0.0,) * 6, 1.0, 40_000_000)
    )
    return episode.EpisodeMapper(
        calibration(),
        limits,
        [sample(i, raw) for i in range(3)],
        follower,
        41_000_000,
    )


def test_different_leader_starts_produce_same_follower_deltas():
    left, right = start(2100), start(2400)
    assert left.first().q == right.first().q == HOME
    a, b = left.target(sample(3, 2110), 61_000_000), right.target(
        sample(3, 2410), 61_000_000
    )
    assert a.q == pytest.approx(b.q)
    for i, q in enumerate(a.q):
        assert q - HOME[i] == pytest.approx(
            (1 if i % 2 == 0 else -1) * 10 * mapping.RADIANS_PER_COUNT
        )
    assert a.created_ns == 60_000_000


def test_no_incremental_integration_or_cross_episode_accumulation():
    mapper = start()
    context = mapper.context()
    for seq, raw in enumerate([2210, 2220, 2210, 2200], 3):
        target = mapper.target(sample(seq, raw), seq * 20_000_000 + 1_000_000)
    assert target.q == HOME
    assert mapper.context() == context
    context["baseline"]["raw"] = ()
    assert mapper.context()["baseline"]["raw"] != ()
    mapper.stop()
    with pytest.raises(model.ControlError, match="ended"):
        mapper.first()
    assert start(2400).first().q == HOME


@pytest.mark.parametrize(
    "bad,now",
    [
        (sample(2), 61_000_000),
        (sample(3, epoch="restart"), 61_000_000),
        (sample(8), 161_000_000),
        (sample(3), 200_000_000),
        (sample(3), 50_000_000),
        (sample(3, 4096), 61_000_000),
    ],
)
def test_bad_stream_latches_until_a_new_episode(bad, now):
    mapper = start()
    with pytest.raises(model.ControlError):
        mapper.target(bad, now)
    with pytest.raises(model.ControlError, match="stopped"):
        mapper.target(sample(4), 81_000_000)


def test_stationary_fresh_follower_home_is_required_but_not_leader_home():
    baseline = model.State(HOME, (0.0,) * 6, 1.0, 40_000_000)
    for value in (
        dataclasses.replace(baseline, q=tuple(q + 0.1 for q in HOME)),
        dataclasses.replace(baseline, qd=(0.1,) * 6),
        dataclasses.replace(baseline, received_ns=50_000_000),
    ):
        with pytest.raises(ValueError, match="follower HOME"):
            start(follower=value)
    assert start(2500).first().q == HOME


def test_limits_remain_absolute_follower_limits():
    limits = model.Limits(
        tuple(q - 0.05 for q in HOME), tuple(q + 0.05 for q in HOME), HOME
    )
    mapper = start(limits=limits)
    with pytest.raises(model.ControlError, match="limit"):
        mapper.target(sample(3, 2300), 61_000_000)


def test_unstable_baseline_is_not_captured():
    with pytest.raises(ValueError, match="moving"):
        episode.EpisodeMapper(
            calibration(),
            model.Limits((-6.0,) * 6, (6.0,) * 6, HOME),
            [sample(0), sample(1), sample(2, 2204)],
            model.State(HOME, (0.0,) * 6, 1.0, 40_000_000),
            41_000_000,
        )
