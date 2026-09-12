"""Native follower execution and ownership without a robot or renderer."""

import dataclasses
import pathlib
import socket
import tempfile
import threading
import time
from unittest import mock

import pytest

from ur12e_collection.control import model, owner
from ur12e_collection.followers import state
from ur12e_collection.followers import dispatch, kinematic, local


@pytest.fixture
def limits():
    return model.Limits(
        lower=(-3.0,) * 6,
        upper=(3.0,) * 6,
        ready=(0.0,) * 6,
        freshness_ns=500_000_000,
    )


def test_home_profile_is_bounded_and_arrives(limits):
    engine = kinematic.Engine(limits, 0)
    engine.command("claim", {}, 0)
    engine.command(
        "move", {"q": [1.0] * 6, "speed": 0.3, "acceleration": 0.5}, 0
    )
    velocities = []
    for i in range(1, 801):
        now = i / 100
        engine.command("heartbeat", {}, now)
        engine.update(now)
        velocities.append(engine.qd[0])
    assert engine.q == (1.0,) * 6
    assert max(map(abs, velocities)) <= 0.3 + 1e-6
    assert (
        max(abs(b - a) * 100 for a, b in zip(velocities, velocities[1:])) <= 0.5
    )


def test_stop_and_watchdog_hold_executed_pose(limits):
    engine = kinematic.Engine(limits, 0)
    engine.command("claim", {}, 0)
    engine.command("servo", {"q": [0.1] * 6}, 0.01)
    engine.update(0.02)
    engine.command(
        "move", {"q": [1.0] * 6, "speed": 0.3, "acceleration": 0.5}, 0.03
    )
    engine.command("stop", {}, 0.04)
    assert engine.update(0.05) == (0.1,) * 6
    engine.update(0.6)
    assert engine.fault and engine.qd == (0.0,) * 6
    with pytest.raises(model.ControlError):
        engine.command("servo", {"q": [0.2] * 6}, 0.61)


def test_native_feedback_does_not_invent_ur_status(limits):
    feedback = state.Feedback((0.0,) * 6, (0.0,) * 6, 1, 10, True, "")
    transport = mock.Mock(read=mock.Mock(return_value=feedback))
    controller = owner.Controller(transport, limits)
    assert controller.tick(10) == feedback
    assert not hasattr(feedback, "robot_mode")
    transport.read.return_value = dataclasses.replace(
        feedback, motion_allowed=False, motion_error="Isaac expired"
    )
    with pytest.raises(model.ControlError, match="Isaac expired"):
        controller.tick(11)
    transport.stop.assert_called_once()


def test_optional_twin_cannot_delay_primary_or_receive_failed_command():
    release = threading.Event()
    mirror = mock.Mock()

    def factory():
        release.wait(2)
        return mirror

    primary = mock.Mock()
    group = dispatch.Group(primary, [factory])
    started = time.monotonic()
    try:
        for _ in range(1000):
            group.servo((0.1,) * 6)
        assert time.monotonic() - started < 0.2
        assert group.twins[0].pending.qsize() == 1
        primary.servo.side_effect = RuntimeError("primary refused")
        with pytest.raises(RuntimeError):
            group.servo((0.2,) * 6)
        operation, args = group.twins[0].pending.get_nowait()
        assert operation == "servo" and args == ((0.1,) * 6,)
        primary.stop.side_effect = RuntimeError("primary stop failed")
        with pytest.raises(RuntimeError):
            group.stop(True)
        assert group.twins[0].pending.get_nowait() == ("stop", (True,))
    finally:
        group.close()
        release.set()
        group.twins[0].worker.join(1)


def test_local_follower_ownership_and_executed_feedback(limits):
    with tempfile.TemporaryDirectory(prefix="native-", dir="/tmp") as temporary:
        service = local.Service(pathlib.Path(temporary) / "f.sock", limits)
        stopped = threading.Event()

        def run():
            while not stopped.is_set():
                service.receive()
                service.engine.update(time.monotonic())
                service.publish()
                stopped.wait(0.005)

        worker = threading.Thread(target=run)
        worker.start()
        transport = None
        try:
            transport = local.Transport(service.endpoint)
            transport.servo((0.1,) * 6)
            deadline = time.monotonic() + 1
            while transport.read().q != (0.1,) * 6:
                assert time.monotonic() < deadline
                time.sleep(0.005)
            transport.stop(True)
            assert transport.read().q == (0.1,) * 6
        finally:
            if transport:
                transport.close()
            stopped.set()
            worker.join(1)
            service.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("sequence", True),
        ("sequence", -1),
        ("created_ns", 1.5),
        ("epoch", ""),
        ("version", True),
        ("version", 2),
        ("operation", "power_on"),
    ],
)
def test_command_boundary_rejects_bad_identity(field, value):
    packet = {
        "version": local.VERSION,
        "sequence": 1,
        "created_ns": 1,
        "epoch": "fixture",
        "operation": "claim",
    }
    packet[field] = value
    with pytest.raises(model.ControlError):
        local.command(local.encode(packet))


def test_stream_frames_preserve_partial_messages_and_bound_memory():
    left, right = socket.socketpair()
    left.setblocking(False)
    frames = local.Frames()
    try:
        right.sendall(b'{"a":')
        assert frames.receive(left) == []
        right.sendall(b'1}\n{"b":2}\n')
        assert frames.receive(left) == [b'{"a":1}', b'{"b":2}']
        right.sendall(b"x" * (local.MAX_PACKET + 1))
        with pytest.raises(model.ControlError, match="oversized"):
            frames.receive(left)
    finally:
        left.close()
        right.close()


def test_service_rejects_expired_reordered_and_foreign_commands(limits):
    with tempfile.TemporaryDirectory(prefix="native-", dir="/tmp") as directory:
        service = local.Service(pathlib.Path(directory) / "f.sock", limits)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        intruder = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        def send(connection, sequence, operation, **fields):
            packet = {
                "version": local.VERSION,
                "epoch": "owner",
                "sequence": sequence,
                "created_ns": time.monotonic_ns(),
                "operation": operation,
                **fields,
            }
            connection.sendall(local.encode(packet) + b"\n")
            service.receive()
            service.engine.update(time.monotonic())

        try:
            client.connect(str(service.endpoint))
            send(client, 1, "claim")
            send(client, 2, "servo", q=[0.1] * 6)
            assert service.engine.q == (0.1,) * 6
            send(client, 2, "servo", q=[0.2] * 6)
            send(client, 3, "servo", q=[0.2] * 6, created_ns=0)
            send(client, 4, "servo", q=[0.2] * 6, epoch="foreign")
            intruder.connect(str(service.endpoint))
            send(intruder, 1, "claim", epoch="intruder")
            send(intruder, 2, "servo", q=[0.2] * 6, epoch="intruder")
            assert service.epoch == "owner"
            assert service.engine.q == (0.1,) * 6
            assert service.sequence == 2
            service.engine.fault = "latched fault"
            send(client, 5, "claim")
            assert service.engine.fault == "latched fault"
        finally:
            client.close()
            intruder.close()
            service.close()


def test_native_source_excludes_acquisition_finishing_after_call(monkeypatch):
    from ur12e_collection.leader import episode, native

    reader = mock.Mock()
    reader.mailbox.view.return_value.health.integers.return_value = (0,) * 7
    first = episode.Sample("device", 1, 1_000_000, 2_000_000, (2000,) * 7)
    future = dataclasses.replace(
        first, sequence=2, start_ns=3_000_000, end_ns=4_000_000
    )
    reader.mailbox.drain.return_value = (
        mock.Mock(sample=first),
        mock.Mock(sample=future),
    )
    monkeypatch.setattr(native.source, "Reader", lambda *args: reader)
    leader = native.Leader("device", 3000000)
    assert leader.samples(3_500_000) == (first,)
    reader.mailbox.view.assert_called_once_with()
    leader.close()
    reader.close.assert_called_once()


def test_follower_configuration_rejects_physical_control_before_paths(tmp_path):
    import json
    from ur12e_collection.followers import config

    path = tmp_path / "teleop.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "recording": False,
                "follower": {"backend": "ur"},
            }
        )
    )
    with pytest.raises(model.ControlError, match="physical"):
        config.load(path)
