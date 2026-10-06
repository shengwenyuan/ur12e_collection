"""HOME-free profiles preserve relative behavior and archive audit semantics."""

import dataclasses
import pathlib

import pytest

from ur12e_collection.control import model, records
from ur12e_collection.leader import (
    audit,
    episode,
    mapping,
    input as leader_input,
)
from test_leader_episode import HOME, calibration, sample
from test_leader_input import Source


def profile():
    old = calibration()
    return dataclasses.replace(
        old,
        home_rad=None,
        joints=tuple(
            dataclasses.replace(j, home_count=None) for j in old.joints
        ),
        gripper_open=None,
        gripper_closed=None,
    )


def mapper(value, raw=2200, follower=None):
    return episode.EpisodeMapper(
        value,
        model.Limits((-6.0,) * 6, (6.0,) * 6, HOME),
        [sample(i, raw) for i in range(3)],
        follower or model.State(HOME, (0.0,) * 6, 1.0, 40_000_000),
        41_000_000,
    )


def test_fixed_home_changes_and_different_starts_do_not_affect_delta():
    old = calibration()
    changed = dataclasses.replace(
        old,
        home_rad=(0.7,) * 6,
        joints=tuple(
            dataclasses.replace(j, home_count=1900) for j in old.joints
        ),
    )
    expected = mapper(old).target(sample(3, 2210), 61_000_000).q
    assert mapper(changed).target(sample(3, 2210), 61_000_000).q == expected
    relative = mapper(profile(), raw=2400)
    assert relative.target(sample(3, 2410), 61_000_000).q == expected
    assert "baseline_calibrated_rad" not in relative.context()
    assert relative.context()["schema_version"] == 2


def test_home_free_roundtrip_and_real_profile():
    value = profile()
    assert mapping.from_document(value.document()) == value
    assert "home_rad" not in value.document()
    assert "home_count" not in value.document()["joints"][0]
    path = pathlib.Path(__file__).parents[1] / "config/gello.relative.json"
    assert mapping.load(path).home_rad is None
    with pytest.raises(ValueError, match="fixed leader HOME"):
        value.angles(sample(0).raw)


@pytest.mark.parametrize(
    "failure", ["home", "sign", "ratio", "interval", "version"]
)
def test_relative_profile_rejects_invalid_configuration(failure):
    document = profile().document()
    if failure == "home":
        document["joints"][0]["home_count"] = 2048
    elif failure == "version":
        document["schema_version"] = 4.0
    else:
        key, value = {
            "sign": ("sign", 0),
            "ratio": ("ratio", 0),
            "interval": ("minimum", 4000),
        }[failure]
        document["joints"][0][key] = value
    with pytest.raises(ValueError):
        mapping.from_document(document)


def test_follower_home_bounds_and_epoch_checks_survive():
    away = model.State((0.0,) * 6, (0.0,) * 6, 1.0, 40_000_000)
    with pytest.raises(ValueError, match="follower HOME"):
        mapper(profile(), follower=away)
    for bad in (sample(3, 4096), sample(3, epoch="reset")):
        active = mapper(profile())
        with pytest.raises(model.ControlError):
            active.target(bad, 61_000_000)
        with pytest.raises(model.ControlError, match="stopped"):
            active.first()


@pytest.mark.parametrize("legacy", [False, True])
def test_audit_supports_home_free_and_historical_context_and_detects_forgery(
    legacy,
):
    source = Source()
    value = calibration() if legacy else profile()
    active = leader_input.Input(
        source,
        value,
        model.Limits((-6.0,) * 6, (6.0,) * 6, HOME),
        model.State(HOME, (0.0,) * 6, 1.0, 41_000_000),
        41_000_000,
    )
    context = active.context()
    if legacy:
        context.update(
            schema_version=1,
            baseline_calibrated_rad=value.angles(sample(2).raw),
        )
    checker = audit.Audit(context, 41_000_000)
    active.sample(41_000_000)
    source.rows = (sample(3, 2210),)
    target = active.sample(61_000_000)
    factory = records.Records(
        {"leader_id": "gello", "command_id": "servo"}, simulated=True
    )
    intent = factory.intent(target, active)
    checker.intent(intent)
    with pytest.raises(ValueError, match="relative mapping"):
        checker.intent(dataclasses.replace(intent, joint_positions_rad=HOME))
