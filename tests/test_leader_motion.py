"""Powered sequencing tested without motor writes or claims about mechanics."""

import dataclasses

import pytest

from ur12e_collection.leader import motion
from ur12e_collection.simulation.motors import Motors


def make(blocked=()):
    motors = Motors((2048, 2048, 2048, 2048, -433, 2048, 3256))
    owner = motion.Motion(
        motors, (2100,) * 7, ((0, 4095),) * 7, blocked=blocked
    )
    motors.advance(1)
    owner.hold(1, motors.bindings())
    for i in range(1, 13):
        motors.advance(1 + i * 20_000_000)
        owner.step(1 + i * 20_000_000)
    assert owner.state == "held"
    return motors, owner


def test_hold_preloads_current_goal_before_torque_and_keeps_power_on_close():
    motors, owner = make()
    assert motors.writes[0][0] == "goals"
    assert motors.writes[0][1][5] == 3663
    assert motors.writes[1][0] == "enable"
    writes = list(motors.writes)
    owner.close()
    assert motors.writes == writes and all(motors.value.torque)


def test_home_waits_for_actual_arrival_and_does_not_accept_old_tolerance():
    motors, owner = make()
    motors.advance(260_000_001)
    owner.go_home(260_000_001)
    assert owner.state == "homing"
    for i in range(14, 100):
        motors.advance(1 + i * 20_000_000)
        owner.step(1 + i * 20_000_000)
    assert owner.state == "held"
    motors.residual = 10
    motors.advance(2_000_000_001)
    with pytest.raises(RuntimeError, match="drift"):
        owner.step(2_000_000_001)


def test_id3_block_preflights_entire_home_before_any_goal():
    motors, owner = make((3,))
    assert not motors.value.torque[2]
    assert all(3 not in value for _, value in motors.writes)
    writes = list(motors.writes)
    motors.advance(260_000_001)
    with pytest.raises(ValueError, match="ID3"):
        owner.go_home(260_000_001)
    assert motors.writes == writes


def test_reset_and_unknown_binding_cannot_trigger_stale_goal():
    motors = Motors()
    owner = motion.Motion(motors, (2000,) * 7, ((0, 4095),) * 7)
    motors.advance(1)
    with pytest.raises(ValueError, match="bindings"):
        owner.hold(1)
    assert not motors.writes
    motors, owner = make()
    motors.advance(260_000_001)
    motors.value = dataclasses.replace(motors.value, epoch="reboot")
    with pytest.raises(RuntimeError, match="reset"):
        owner.step(260_000_001)


def test_arrival_timeout_latches_failure():
    motors, owner = make()
    motors.advance(260_000_001)
    owner.go_home(260_000_001)
    motors.residual = 20
    motors.advance(31_000_000_001)
    with pytest.raises(TimeoutError):
        owner.step(31_000_000_001)
    assert owner.state == "fault"


def test_fresh_duplicate_readback_does_not_fabricate_acquisition_progress():
    motors, owner = make()
    original = motors.value
    assert owner.step(original.received_ns + 20_000_000) == "held"
    assert owner.previous == original
    with pytest.raises(RuntimeError, match="stale"):
        owner.step(original.received_ns + 100_000_001)
    assert owner.state == "fault"


def test_reused_receipt_cannot_hide_changed_motor_state():
    motors, owner = make()
    motors.value = dataclasses.replace(motors.value, counts=(2000,) * 7)
    with pytest.raises(RuntimeError, match="faulty"):
        owner.step(motors.value.received_ns + 20_000_000)


def test_arrival_dwell_uses_observed_time_instead_of_delivery_delay():
    motors = Motors()
    owner = motion.Motion(motors, (2048,) * 7, ((0, 4095),) * 7, blocked=())
    motors.advance(1)
    owner.hold(1, motors.bindings())
    motors.advance(10_000_001)
    assert owner.step(100_000_001) == "holding"
    motors.advance(150_000_001)
    assert owner.step(250_000_001) == "holding"
    motors.advance(211_000_001)
    assert owner.step(310_000_001) == "held"


def test_coordinator_traverses_ready_leading_hold_and_blocks_clearance():
    from ur12e_collection.leader.coordinator import Coordinator

    motors = Motors()
    owner = motion.Motion(motors, (2100,) * 7, ((0, 4095),) * 7, blocked=())
    coupled = Coordinator(owner, motors.bindings, supported=True)
    motors.advance(1)
    coupled.start_home(1)
    ready = False
    for i in range(1, 50):
        motors.advance(1 + i * 20_000_000)
        ready = coupled.home_ready(1 + i * 20_000_000)
        if ready:
            break
    assert ready
    coupled.begin()
    assert not any(motors.value.torque)
    motors.value = dataclasses.replace(motors.value, counts=(2200,) * 7)
    motors.advance(2_000_000_001)
    coupled.hold(2_000_000_001)
    for i in range(1, 13):
        motors.advance(2_000_000_001 + i * 20_000_000)
        settled = coupled.held(2_000_000_001 + i * 20_000_000)
    assert settled and motors.value.counts == (2200,) * 7
    assert all(motors.value.torque)
    before = list(motors.writes)
    coupled.close()
    assert motors.writes == before
    blocked = Coordinator(
        motion.Motion(Motors(), (2100,) * 7, ((0, 4095),) * 7),
        lambda: None,
        supported=True,
    )
    with pytest.raises(RuntimeError, match="clearance"):
        blocked.start_home(1)
