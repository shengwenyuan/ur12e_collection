"""Physical authorization, bounded input and operator transition contracts."""

import dataclasses
import json
import math
from pathlib import Path
from unittest import mock

import pytest

from ur12e_collection.control import conditioning, guards, model, teleop
from ur12e_collection.followers import config, state
from ur12e_collection.leader import episode, mapping
from ur12e_collection.physical import network, preflight, tool

ROOT = Path(__file__).parents[1]


def configuration():
    return config.load(ROOT / "config/teleop.ur.json")


def sample(raw, sequence=0, stamp=1_000_000_000):
    return episode.Sample("fixture", sequence, stamp, stamp, (raw,) * 7)


def test_physical_profile_has_separate_units_and_conservative_bounds():
    value = configuration()
    assert value["limits"].speed == math.radians(12)
    assert value["limits"].ready_speed == math.radians(3)
    assert value["limits"].acceleration == math.radians(15)
    assert value["limits"].ready_acceleration == math.radians(6)
    assert value["guards"].measured_speed == math.radians(14.4)
    assert value["home_open_gripper"] is False
    assert value["gripper"]["speed"] == value["gripper"]["force"] == 32


def test_home_proximity_is_required_only_at_episode_engagement():
    from test_leader_episode import start, sample as leader_sample

    limits = configuration()["limits"]
    away = (math.radians(6), *limits.ready[1:])
    feedback = model.State(away, (0.0,) * 6, 1.0, 40_000_000)
    with pytest.raises(ValueError, match="follower HOME required"):
        start(limits=limits, follower=feedback)
    mapper = start(limits=limits)
    reading = dataclasses.replace(
        leader_sample(3), raw=(2270,) + (2200,) * 5 + (3200,)
    )
    desired = mapper.target(reading, 61_000_000)
    assert math.degrees(desired.q[0]) > 6
    limits.check(desired.q)
    # The same target is invalid as a new engagement reference.
    with pytest.raises(ValueError, match="follower HOME required"):
        start(
            limits=limits, follower=dataclasses.replace(feedback, q=desired.q)
        )


@pytest.mark.parametrize("angle", [6, 30])
def test_following_can_cross_old_home_box_without_exceeding_rates(angle):
    limits = configuration()["limits"]
    previous = model.Target(limits.ready, 0, 1_000_000_000)
    bounded = conditioning.Conditioner(limits, previous)
    desired = (math.radians(angle), *limits.ready[1:])
    velocity = (0.0,) * 6
    for _ in range(1800):
        target = bounded.step(desired, previous.created_ns + 8_333_333)
        dt = (target.created_ns - previous.created_ns) / 1e9
        current = tuple((a - b) / dt for a, b in zip(target.q, previous.q))
        assert max(map(abs, current)) <= limits.speed
        assert (
            max(abs(a - b) / dt for a, b in zip(current, velocity))
            <= limits.acceleration
        )
        limits.check(target.q)
        previous, velocity = target, current
    assert target.q == pytest.approx(desired, abs=1e-7)


@pytest.mark.parametrize("axis", range(6))
def test_operating_bounds_still_reject_each_joint(axis):
    limits = configuration()["limits"]
    for edge, offset in ((limits.lower, -0.001), (limits.upper, 0.001)):
        q = list(limits.ready)
        q[axis] = edge[axis] + offset
        with pytest.raises(model.ControlError, match="joint limit"):
            limits.check(tuple(q))


@pytest.mark.parametrize(
    "change",
    [
        {"speed": 1},
        {"ready_speed": 0.3},
        {"freshness_ns": 500_000_000},
        {"stopped_speed": 0.01},
        {"arrival": 0.01},
    ],
)
def test_physical_rejects_inherited_sim_limits(tmp_path, change):
    value = json.loads((ROOT / "config/teleop.ur.json").read_text())
    value["limits"].update(change)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value))
    with pytest.raises((ValueError, model.ControlError)):
        config.load(path)


def test_unsigned_physical_launch_never_calls_device_factory():
    with (
        mock.patch("sys.platform", "linux"),
        mock.patch(
            "ur12e_collection.physical.transport.open_transport"
        ) as opening,
    ):
        with pytest.raises(model.ControlError, match="operator-approved"):
            teleop.run(ROOT / "config/teleop.ur.json", mock.Mock())
        opening.assert_not_called()


def test_in_range_encoder_jump_rejected_before_conditioning():
    policy = configuration()["guards"]
    before = sample(3000)
    policy.input(before, sample(3002, 1, 1_008_333_333))
    with pytest.raises(model.ControlError, match="jumped"):
        policy.input(before, sample(3300, 1, 1_008_333_333))


def test_intent_lag_allows_thirty_degrees_and_rejects_larger_error():
    policy = configuration()["guards"]
    for angle in (10.1, 29.99, 30):
        policy.intent((math.radians(angle),) * 6, (0.0,) * 6)
    with pytest.raises(model.ControlError, match="outran"):
        policy.intent((math.radians(30.01),) * 6, (0.0,) * 6)


def test_gripper_encoder_jump_is_not_hidden_by_saturation():
    policy = configuration()["guards"]
    before = sample(3000)
    after = dataclasses.replace(
        sample(3000, 1, 1_008_333_333), raw=(3000,) * 6 + (0,)
    )
    with pytest.raises(model.ControlError, match="jumped"):
        policy.input(before, after)


def test_tracking_grace_resets_and_requires_advancing_feedback():
    monitor = guards.Tracking(configuration()["guards"])
    feedback = model.State((0.0,) * 6, (0.0,) * 6, 1, 1)
    monitor.check((0.05,) * 6, feedback, 1_000_000_000)
    monitor.check((0.05,) * 6, feedback, 2_000_000_000)
    monitor.check((math.radians(1.25),) * 6, feedback, 2_000_000_000)
    monitor.check(
        (math.radians(2),) * 6,
        dataclasses.replace(feedback, timestamp=1.5),
        2_500_000_000,
    )
    monitor.check((0.05,) * 6, feedback, 3_000_000_000)
    with pytest.raises(model.ControlError, match="tracking"):
        monitor.check(
            (0.05,) * 6,
            dataclasses.replace(feedback, timestamp=1.3),
            3_300_000_000,
        )
    with pytest.raises(model.ControlError, match="speed"):
        monitor.check(
            (0.0,) * 6,
            dataclasses.replace(feedback, qd=(1.0,) * 6),
            4_000_000_000,
        )


def session():
    value = configuration()
    calibration = mapping.load(value["leader"]["calibration"])
    device = mock.Mock()
    instance = teleop.Teleoperation(
        device,
        mock.Mock(),
        calibration,
        value["limits"],
        home_open_gripper=False,
    )
    instance.controller.progress.feedback = state.Feedback(
        value["limits"].ready,
        (0.0,) * 6,
        1,
        1_000_000_000,
        True,
        "",
    )
    return instance, device


def test_home_never_opens_real_gripper_and_space_cancels_home():
    instance, device = session()
    instance.key(" ", 1_000_000_000)
    assert instance.state == "homing"
    device.gripper.assert_not_called()
    instance.key(" ", 2_000_000_000)
    assert instance.state == "stopping"
    device.stop.assert_called_once_with(False)
    instance.key(" ", 3_000_000_000)
    assert device.move.call_count == 1


def test_autorepeat_does_not_queue_home_start_stop():
    instance, device = session()
    instance.key(" ", 1_000_000_000)
    for offset in range(1, 20):
        instance.key(" ", 1_000_000_000 + offset * 100_000_000)
    assert instance.state == "homing"
    device.stop.assert_not_called()
    assert device.move.call_count == 1


def test_ready_with_closed_gripper_cannot_capture_new_reference():
    instance, _ = session()
    instance.state = "ready"
    instance.controller.progress.feedback = dataclasses.replace(
        instance.controller.progress.feedback,
        gripper_position=128,
        gripper_open=False,
    )
    instance.key(" ", 2_000_000_000)
    assert instance.state == "ready"


def test_failed_identity_uses_no_control_or_tool_connection():
    value = configuration()
    with (
        mock.patch.object(network, "route", return_value={}),
        mock.patch(
            "ur12e_collection.ur.dashboard",
            return_value={
                "state": "available",
                "responses": {"get serial number": "wrong"},
            },
        ),
    ):
        with pytest.raises(model.ControlError, match="identity"):
            preflight.identity(value, True)


def test_required_gripper_fault_blocks_targets_and_hold_clears_pending():
    worker = tool.Worker("unused", {"port": 63352})
    with mock.patch.object(worker, "view"):
        worker.offer(255)
        worker.hold()
        assert worker.pending is None
    worker.error = "lost required gripper"
    with pytest.raises(RuntimeError, match="lost required"):
        worker.offer(0)


def test_loss_check_does_not_accept_100_percent_loss():
    with (
        mock.patch.object(network, "route", return_value={}),
        mock.patch(
            "subprocess.run",
            return_value=mock.Mock(
                returncode=0,
                stdout="5 transmitted, 0 received, 100% packet loss",
            ),
        ),
    ):
        with pytest.raises(ValueError, match="lost packets"):
            network.check("10.0.0.2", "eth0")


@pytest.mark.parametrize(
    "gateway,iface,wireless",
    [(1, "eth0", False), (0, "wlan0", False), (0, "eth0", True)],
)
def test_route_rejects_gateway_interface_mismatch_or_wifi(
    tmp_path, gateway, iface, wireless
):
    (tmp_path / "proc/net").mkdir(parents=True)
    # 10.0.0.2, little-endian route encoding, direct /24.
    (tmp_path / "proc/net/route").write_text(
        f"header\n{iface} 0000000A {gateway:08X} 0001 0 0 0 00FFFFFF 0 0 0\n"
    )
    device = tmp_path / "sys/class/net" / iface
    device.mkdir(parents=True)
    if wireless:
        (device / "wireless").mkdir()
    with mock.patch("sys.platform", "linux"):
        with pytest.raises(ValueError, match="direct wired"):
            network.route("10.0.0.2", "eth0", tmp_path)


def test_slow_stop_retains_observation_and_serializes_watchdog_writes():
    import threading
    from ur12e_collection.physical import stopping

    sdk = mock.Mock()
    entered, release = threading.Event(), threading.Event()

    def brake(_value):
        entered.set()
        release.wait(2)
        return True

    sdk.servoStop.side_effect = brake
    stop = stopping.Stop(sdk, True, 0.1, mock.Mock())
    stop.start()
    try:
        assert entered.wait(1)
        assert not stop.done.is_set()
        sdk.setWatchdog.assert_called_once_with(0.5)
    finally:
        release.set()
        stop.join()
    assert sdk.setWatchdog.call_args_list == [mock.call(0.5), mock.call(5.0)]
    sdk.servoStop.assert_called_once_with(0.1)
    sdk.stopJ.assert_not_called()


def test_failed_stop_acknowledgement_is_not_success():
    from ur12e_collection.physical import stopping

    sdk = mock.Mock()
    sdk.servoStop.return_value = False
    stop = stopping.Stop(sdk, True, 0.1, mock.Mock())
    stop.start()
    with pytest.raises(model.ControlError, match="acknowledge"):
        stop.join()
    assert stop.done.is_set()


def test_home_stop_uses_joint_deceleration_and_cancels_tool_pending():
    from ur12e_collection.physical import transport

    sdk, worker = mock.Mock(), mock.Mock()
    device = transport.Transport(sdk, mock.Mock(), worker, configuration())
    device.stop(False)
    device.stopping.join()
    sdk.stopJ.assert_called_once_with(math.radians(2), True)
    sdk.servoStop.assert_not_called()
    worker.hold.assert_called_once()


def test_evidence_failure_cannot_prevent_stop_dispatch():
    from ur12e_collection.physical import transport

    sdk = mock.Mock()
    device = transport.Transport(
        sdk,
        mock.Mock(),
        mock.Mock(),
        configuration(),
        emit=mock.Mock(side_effect=RuntimeError("disk full")),
    )
    device.stop(False)
    device.stopping.join()
    sdk.stopJ.assert_called_once()


def test_physical_gripper_contact_is_distinct_from_requested_closure():
    import time
    from ur12e_collection.physical import transport

    rx = mock.Mock()
    rx.getTimestamp.return_value = 1
    rx.getActualQ.return_value = configuration()["limits"].ready
    rx.getActualQd.return_value = (0.0,) * 6
    rx.getRobotMode.return_value = 7
    rx.getSafetyMode.return_value = 1
    rx.getRuntimeState.return_value = 2
    rx.getActualCurrent.return_value = (0.0,) * 6
    rx.getActualTCPPose.return_value = (0.0,) * 6
    worker = mock.Mock()
    worker.view.return_value = tool.Reading(
        (("POS", 128), ("PRE", 255), ("OBJ", 2)), time.monotonic_ns()
    )
    device = transport.Transport(mock.Mock(), rx, worker, configuration())
    feedback = device.read()
    assert not feedback.gripper_open
    assert dict(feedback.gripper_registers)["POS"] == 128
    assert dict(feedback.gripper_registers)["PRE"] == 255


def test_trace_writes_source_times_and_reports_serialization_failure(tmp_path):
    from ur12e_collection.control import trace

    writer = trace.Trace(tmp_path / "evidence")
    writer.emit("sample", leader=sample(3000))
    writer.close()
    row = json.loads(writer.path.read_text())
    assert row["leader"]["start_ns"] == 1_000_000_000
    assert row["monotonic_ns"] > 0


def test_stopped_tool_intent_does_not_leak_into_next_home():
    from ur12e_collection.followers import dispatch

    primary = mock.Mock()
    group = dispatch.Group(primary)
    group.gripper(200)
    group.servo((0.0,) * 6)
    group.stop(True)
    group.move((0.0,) * 6, 0.01, 0.02)
    primary.move.assert_called_once_with((0.0,) * 6, 0.01, 0.02)


@pytest.mark.parametrize("phase", ["ready", "held", "post_stop"])
@pytest.mark.parametrize(
    "speed,drift,rejected",
    [(0.0106, 0, False), (0.049, 0, False), (0.051, 0, True), (0, 0.051, True)],
)
def test_hold_monitor_tolerates_noise_but_keeps_speed_and_drift_bounds(
    phase, speed, drift, rejected
):
    from ur12e_collection.physical import transport

    value = configuration()
    home = value["limits"].ready
    feedback = model.State(
        (home[0] + math.radians(drift), *home[1:]),
        (math.radians(speed), 0, 0, 0, 0, 0),
        1,
        1_000_000_000,
        runtime_state=1,
    )
    if phase == "post_stop":
        device = transport.Transport(
            mock.Mock(), mock.Mock(), mock.Mock(), value
        )
        with (
            mock.patch.object(transport, "read_state", return_value=feedback),
            mock.patch.object(
                transport.time, "monotonic", side_effect=[0, 0, 0, 0.01, 31]
            ),
            mock.patch.object(transport.time, "sleep"),
        ):
            if rejected:
                with pytest.raises(
                    model.ControlError, match="hold not confirmed"
                ):
                    device.observe_hold(home)
            else:
                device.observe_hold(home)
    else:
        instance, _ = session()
        instance.state, instance.held = phase, home
        instance.guards = value["guards"]
        instance.controller = mock.Mock()
        instance.controller.progress.feedback = feedback
        if rejected:
            with pytest.raises(model.ControlError, match="moved while held"):
                instance.step(1_000_000_000)
        else:
            instance.step(1_000_000_000)


def test_hold_noise_does_not_relax_initial_stop_confirmation():
    from ur12e_collection.control import settling

    monitor = settling.Standstill()
    for index in range(40):
        assert not monitor.update(
            (math.radians(0.02),) * 6,
            1 + index * 0.01,
            1_000_000_000 + index * 10_000_000,
        )


@pytest.mark.parametrize(
    "scenario,reason",
    [
        ("startup", None),
        ("timeout", "startup timed out"),
        ("stale", "feedback stale"),
        ("regression", "timestamp regressed"),
        ("unsafe", "controller modes"),
        ("position", "displacement"),
        ("speed", "joint speed"),
    ],
)
def test_handover_reports_feedback_and_waits_only_for_normal_startup(
    scenario, reason, capsys
):
    limits = configuration()["limits"]
    before = model.State(limits.ready, (0.0,) * 6, 1, 0, runtime_state=1)
    clock, reads = [0], [0]
    events = mock.Mock()

    def read():
        clock[0] += 20_000_000
        reads[0] += 1
        after = dataclasses.replace(
            before,
            received_ns=clock[0],
            timestamp=1 + reads[0] * 0.02,
            runtime_state=1 if reads[0] < 3 or scenario == "timeout" else 2,
        )
        if scenario == "stale":
            return dataclasses.replace(after, timestamp=1)
        if scenario == "regression":
            return dataclasses.replace(after, timestamp=0.5)
        if scenario == "unsafe":
            return dataclasses.replace(after, safety_mode=3)
        if scenario == "position":
            return dataclasses.replace(after, q=(0.01, *limits.ready[1:]))
        if scenario == "speed":
            return dataclasses.replace(after, qd=(math.radians(0.02),) * 6)
        return after

    with (
        mock.patch.object(
            preflight.time, "monotonic_ns", side_effect=lambda: clock[0]
        ),
        mock.patch.object(preflight.time, "sleep"),
    ):
        if reason:
            with pytest.raises(model.ControlError, match=reason) as error:
                preflight.handover(read, before, limits, events)
            assert "modes=" in str(error.value)
            assert events.call_args.kwargs["outcome"] == "rejected"
        else:
            assert preflight.handover(
                read, before, limits, events
            ).motion_allowed
            assert reads[0] == 3
            assert events.call_args.kwargs["outcome"] == "accepted"
            assert "Handover accepted" in capsys.readouterr().out
    assert events.call_args_list[0] == mock.call(
        "handover_before", feedback=before
    )


def test_unstable_leader_retries_without_engaging_or_repeating_warning(capsys):
    instance, device = session()
    instance.state = "engaging"
    with mock.patch(
        "ur12e_collection.control.teleop.leader_input.Input",
        side_effect=episode.UnstableReference("moving"),
    ):
        instance._engage(1_000_000_000)
        instance._engage(1_000_000_001)
    assert instance.state == "waiting_leader"
    assert capsys.readouterr().out.count("retrying") == 1
    device.servo.assert_not_called()
    instance.key(" ", 2_000_000_000)
    assert instance.state == "ready"


def test_nontransient_leader_failure_is_not_retried():
    instance, _ = session()
    instance.state = "engaging"
    with mock.patch(
        "ur12e_collection.control.teleop.leader_input.Input",
        side_effect=ValueError("stale leader sample"),
    ):
        with pytest.raises(ValueError, match="stale"):
            instance._engage(1_000_000_000)


def test_gripper_input_rate_is_independent_and_rejection_names_axis():
    policy = configuration()["guards"]
    assert policy.gripper_input_rate == math.radians(720)
    before = sample(3000)
    later = dataclasses.replace(
        sample(3000, 1, 1_008_333_333), raw=(3000,) * 6 + (3060,)
    )
    policy.input(before, later)
    arm_jump = dataclasses.replace(later, raw=(3060,) + (3000,) * 6)
    with pytest.raises(model.ControlError, match="axis=j1.*delta_counts=60"):
        policy.input(before, arm_jump)
    gripper_jump = dataclasses.replace(later, raw=(3000,) * 6 + (3100,))
    with pytest.raises(model.ControlError, match="axis=gripper.*previous=3000"):
        policy.input(before, gripper_jump)


def test_rejection_stops_without_closing_control_or_releasing_tool():
    instance, device = session()
    instance.state = "following"
    instance.controller.progress.state = "following"
    instance.input = mock.Mock()
    instance.reject("input rejected", 2_000_000_000)
    assert instance.state == "stopping"
    instance.input.close.assert_called_once()
    device.stop.assert_called_once_with(True)
    device.close.assert_not_called()
    device.gripper.assert_not_called()


def test_failed_controller_stays_blocked_without_another_stop_or_reconnect():
    instance, device = session()
    instance.controller.progress.state = "fault"
    instance.reject("transport failed", 2_000_000_000)
    assert instance.state == "blocked"
    device.stop.assert_not_called()
    device.close.assert_not_called()


@pytest.mark.parametrize("state", ["stopping", "held"])
def test_rejection_does_not_restart_stop_supervision(state):
    instance, device = session()
    instance.state = state
    instance.controller.progress.state = (
        "stopping" if state == "stopping" else "hold"
    )
    instance.reject("late recording error", 2_000_000_000)
    assert instance.state == state
    device.stop.assert_not_called()
    device.close.assert_not_called()
