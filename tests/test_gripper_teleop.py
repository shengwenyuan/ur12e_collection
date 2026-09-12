"""Relative gripper mapping and atomic native arm/tool execution."""

import dataclasses
import math
import threading
from unittest import mock

import pytest

from ur12e_collection.control import model
from ur12e_collection.followers import dispatch, kinematic
from ur12e_collection.leader import mapping


@pytest.mark.parametrize("origin", [-1900, 0, 3388, 8900])
@pytest.mark.parametrize("sign", [-1, 1])
def test_relative_gripper_uses_one_immutable_open_reference(origin, sign):
    reference = mapping.GripperReference(origin, sign)
    for delta, expected in [
        (0, 0),
        (256, 128),
        (512, 255),
        (800, 255),
        (600, 255),
        (256, 128),
        (0, 0),
        (-200, 0),
        (128, 64),
    ]:
        assert reference.position(origin + sign * delta) == expected
    assert reference.count == origin
    restarted = mapping.GripperReference(origin + 800, sign)
    assert restarted.position(origin + 800) == 0


def test_gripper_reference_and_command_reject_invalid_values():
    for sign in (0, 2, True):
        with pytest.raises(ValueError):
            mapping.GripperReference(0, sign)
    reference = mapping.GripperReference(0, 1)
    for count in (True, 1.5, 2**31):
        with pytest.raises(ValueError):
            reference.position(count)
    for value in (True, -1, 256, math.nan, math.inf):
        with pytest.raises(model.ControlError):
            kinematic.gripper_position(value)


def engine():
    limits = model.Limits(lower=(-3.0,) * 6, upper=(3.0,) * 6, ready=(0.0,) * 6)
    return kinematic.Engine(limits, 0)


@pytest.mark.parametrize("stop", ["stop", "release", "watchdog"])
def test_gripper_rate_and_interruption_hold_executed_aperture(stop):
    follower = engine()
    follower.command("claim", {}, 0)
    follower.command("servo", {"q": [0.0] * 6, "gripper_position": 255}, 0)
    follower.update(0.25)
    assert follower.gripper_position == 63.75
    assert follower.q == (0.0,) * 6
    if stop != "watchdog":
        follower.command(stop, {}, 0.25)
    follower.update(0.8)
    assert follower.gripper_position == 63.75
    follower.update(0.9)
    assert follower.gripper_position == 63.75
    if stop == "watchdog":
        assert follower.fault


def test_gripper_opening_and_arm_motion_are_independent():
    follower = engine()
    follower.command("claim", {}, 0)
    follower.command("servo", {"q": [0.0] * 6, "gripper_position": 255}, 0)
    for step in range(1, 5):
        now = step * 0.25
        follower.command("heartbeat", {}, now)
        follower.update(now)
    assert follower.gripper_position == 255
    follower.command("servo", {"q": [0.2] * 6}, 1.1)
    follower.update(1.2)
    assert follower.q == (0.2,) * 6
    assert follower.gripper_position == 255
    follower.command(
        "move",
        {
            "q": [0.0] * 6,
            "speed": 0.3,
            "acceleration": 0.5,
            "gripper_position": 0,
        },
        1.2,
    )
    for step in range(1, 10):
        now = 1.2 + step * 0.25
        follower.command("heartbeat", {}, now)
        follower.update(now)
    assert follower.gripper_position == 0
    assert follower.q == (0.0,) * 6


def test_optional_twin_receives_atomic_latest_arm_and_gripper():
    release = threading.Event()
    primary = mock.Mock()

    def delayed_twin():
        release.wait(2)
        return mock.Mock()

    group = dispatch.Group(primary, [delayed_twin])
    try:
        group.gripper(128)
        group.servo((0.1,) * 6)
        group.gripper(255)
        group.servo((0.2,) * 6)
        primary.servo.assert_called_with((0.2,) * 6, 255)
        assert group.twins[0].pending.get_nowait() == (
            "servo",
            ((0.2,) * 6, 255),
        )
        group.gripper(0)
        group.move((0.0,) * 6, 0.3, 0.5)
        primary.move.assert_called_with((0.0,) * 6, 0.3, 0.5, 0)
        group.stop(True)
        assert group.twins[0].pending.get_nowait() == ("stop", (True,))
    finally:
        group.close()
        release.set()
        group.twins[0].worker.join(1)


def test_simulated_gripper_feedback_validates_its_own_domain():
    feedback = kinematic.Feedback((0.0,) * 6, (0.0,) * 6, 1, 1, True, "")
    assert (
        dataclasses.replace(feedback, gripper_position=127.5).gripper_position
        == 127.5
    )
    with pytest.raises(model.ControlError):
        dataclasses.replace(feedback, gripper_position=math.nan)


@pytest.mark.parametrize("age", [-1, 100_000_001])
def test_engagement_waits_for_fresh_feedback_before_capturing_origin(age):
    from pathlib import Path
    from ur12e_collection.control import teleop
    from ur12e_collection.leader import episode

    calibration = mapping.load(
        Path(__file__).parents[1] / "config/gello.calibration-20260912.json"
    )
    limits = model.Limits(
        lower=(-3.0,) * 6,
        upper=(3.0,) * 6,
        ready=calibration.home_rad,
        freshness_ns=500_000_000,
    )
    now = 1_000_000_000
    feedback = kinematic.Feedback(
        limits.ready, (0.0,) * 6, 1, now - age, True, ""
    )
    source = mock.Mock()
    raw = tuple(j.home_count for j in calibration.joints) + (4321,)
    source.samples.return_value = tuple(
        episode.Sample(
            "fixture",
            i,
            now - (6 - i) * 10_000_000,
            now - (6 - i) * 10_000_000,
            raw,
        )
        for i in range(7)
    )
    session = teleop.Teleoperation(mock.Mock(), source, calibration, limits)
    session.state = "engaging"
    session.controller.progress.feedback = feedback
    session._engage(now)
    assert session.state == "engaging" and session.gripper_reference is None
    source.samples.assert_not_called()
    session.controller.progress.feedback = dataclasses.replace(
        feedback, received_ns=now
    )
    session._engage(now)
    assert session.state == "following"
    assert session.gripper_reference.count == 4321
    assert session.gripper_reference.position(4321) == 0
    session.close()
