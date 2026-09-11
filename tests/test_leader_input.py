"""Source reuse, conditioning and archived provenance remain independently safe."""

import dataclasses

import pytest

from ur12e_collection.control import conditioning, model, records
from ur12e_collection.leader import audit, episode, input as leader_input
from test_leader_episode import calibration, sample, HOME


class Source:
    origin = {"kind": "test"}

    def __init__(self):
        self.rows = tuple(sample(i) for i in range(3))

    def samples(self, _now):
        return self.rows


def make():
    source = Source()
    limits = model.Limits((-6.0,) * 6, (6.0,) * 6, HOME)
    follower = model.State(HOME, (0.0,) * 6, 1.0, 41_000_000)
    return source, leader_input.Input(
        source, calibration(), limits, follower, 41_000_000
    )


def test_fresh_reuse_does_not_refresh_source_and_stale_input_stops():
    source, active = make()
    assert active.sample(41_000_000).q == HOME
    active.sample(61_000_000)
    assert active.evidence()["sequence"] == 2
    assert active.evidence()["start_ns"] == 40_000_000
    with pytest.raises(model.ControlError, match="stale"):
        active.sample(141_000_001)
    source.rows = (sample(8),)
    # An Input failure is latched by the session; explicit close retires mapper.
    active.close()
    with pytest.raises(model.ControlError, match="ended"):
        active.sample(161_000_000)


def test_acquisition_reset_cannot_rebase_active_episode():
    source, active = make()
    active.sample(41_000_000)
    source.rows = (sample(3, epoch="new"),)
    with pytest.raises(model.ControlError, match="epoch"):
        active.sample(61_000_000)


def test_conditioned_motion_respects_limits_on_jitter_and_reversal():
    limits = model.Limits((-6.0,) * 6, (6.0,) * 6, HOME)
    previous = model.Target(HOME, 0, 1_000_000_000)
    bounded = conditioning.Conditioner(limits, previous)
    velocity = (0.0,) * 6
    now = previous.created_ns
    for i in range(1200):
        dt_ns = (17, 23, 20, 25, 15)[i % 5] * 1_000_000
        now += dt_ns
        desired = tuple(q + (0.8 if i < 400 else -0.6) for q in HOME)
        target = bounded.step(desired, now)
        dt = dt_ns / 1e9
        current = tuple((a - b) / dt for a, b in zip(target.q, previous.q))
        assert max(map(abs, current)) <= limits.speed
        assert (
            max(abs(a - b) / dt for a, b in zip(current, velocity))
            <= limits.acceleration
        )
        previous, velocity = target, current
    assert target.q == pytest.approx(desired, abs=1e-7)
    with pytest.raises(model.ControlError):
        bounded.step((100.0,) * 6, now + 20_000_000)


def test_independent_audit_rejects_forged_raw_intent_and_fast_command():
    source, active = make()
    checker = audit.Audit(active.context(), 41_000_000)
    active.sample(41_000_000)
    source.rows = (sample(3, 2400),)
    target = active.sample(61_000_000)
    writer = records.Records(
        {"leader_id": "gello", "command_id": "servo"}, simulated=True
    )
    intent = writer.intent(target, active)
    checker.intent(intent)
    checker.sent(writer.sent(target, 62_000_000))
    with pytest.raises(ValueError, match="raw relative"):
        checker.intent(dataclasses.replace(intent, joint_positions_rad=HOME))
    source.rows = (sample(4, 2410),)
    target = active.sample(81_000_000)
    checker.intent(writer.intent(target, active))
    with pytest.raises(ValueError, match="derivatives"):
        checker.sent(
            writer.sent(dataclasses.replace(target, q=(0.0,) * 6), 82_000_000)
        )
