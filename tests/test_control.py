"""Control gates without SDK imports, sockets or physical motion."""

import dataclasses

import pytest

from ur12e_collection.control import backends, model, owner
from ur12e_collection.simulation import profile
from ur12e_collection.simulation.connection import Lease

NOW = 1_000_000_000


class FakeTransport:
    """Record commands separately from explicit measured feedback."""

    def __init__(self):
        self.feedback = model.State(profile.HOME, (0.0,) * 6, 1.0, NOW)
        self.calls = []

    def read(self):
        return self.feedback

    def move(self, q, speed, acceleration):
        self.calls.append(("move", q, speed, acceleration))

    def servo(self, q):
        self.calls.append(("servo", q))

    def stop(self, servo):
        self.calls.append(("stop", servo))

    def heartbeat(self):
        self.calls.append(("heartbeat",))

    def close(self):
        self.calls.append(("close",))


def setup():
    transport = FakeTransport()
    control = owner.Controller(transport, profile.LIMITS)
    control.tick(NOW)
    return transport, control


def shifted(value):
    return (value, *profile.HOME[1:])


@pytest.mark.parametrize("backend", ["hardware", "physical", "127.0.0.1", ""])
def test_physical_factory_rejects_without_connection(backend, monkeypatch):
    import socket

    def forbidden(*_args, **_kwargs):
        pytest.fail("physical factory attempted a connection")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    with pytest.raises(model.ControlError, match="disabled"):
        backends.open_backend(backend)


def test_second_owner_is_rejected_and_release_is_reusable(tmp_path):
    path = tmp_path / "controller.lock"
    first = Lease(path)
    with pytest.raises(model.ControlError, match="another controller"):
        Lease(path)
    first.close()
    Lease(path).close()


@pytest.mark.parametrize(
    "q",
    [tuple(), [0] * 6, (float("nan"),) * 6, (float("inf"),) * 6, (True,) * 6],
)
def test_malformed_joints(q):
    with pytest.raises(model.ControlError):
        model.Target(q, 0, NOW)


def test_ready_limits_and_measured_arrival():
    transport, control = setup()
    control.go_ready(NOW)
    assert transport.calls[-1] == ("move", profile.HOME, 0.3, 0.5)
    assert control.state == "moving"
    control.tick(NOW)
    transport.feedback = dataclasses.replace(
        transport.feedback, timestamp=1.12, received_ns=NOW + 120_000_000
    )
    control.tick(NOW + 120_000_000)
    assert control.state == "hold"


@pytest.mark.parametrize(
    "points,start",
    [
        ((shifted(0.2), shifted(6.0)), profile.HOME),
        ((profile.HOME,), shifted(0.5)),
    ],
)
def test_invalid_complete_route_sends_no_motion(points, start):
    transport, control = setup()
    with pytest.raises(model.ControlError):
        control.route(points, start, NOW)
    assert not any(c[0] == "move" for c in transport.calls)
    assert control.state == "fault"
    with pytest.raises(model.ControlError):
        control.go_ready(NOW)


def test_angle_branch_is_preserved():
    transport, control = setup()
    control.route((shifted(5.0), shifted(-5.0)), profile.HOME, NOW)
    assert transport.calls[-1][1][0] == 5.0
    assert control.progress.route[0][0] == -5.0


@pytest.mark.parametrize(
    "q,sequence,stamp,message",
    [
        (shifted(6.0), 1, NOW + 20_000_000, "joint limit"),
        (shifted(0.09), 1, NOW + 20_000_000, "step"),
        (shifted(0.04), 1, NOW + 20_000_000, "velocity"),
        (shifted(0.01), 1, NOW + 20_000_000, "acceleration"),
        (profile.HOME, 0, NOW + 20_000_000, "sequence"),
        (profile.HOME, 1, NOW, "time"),
        (profile.HOME, 1, NOW + 300_000_000, "gap"),
    ],
)
def test_bad_leader_target_faults_before_send(q, sequence, stamp, message):
    transport, control = setup()
    control.engage(model.Target(profile.HOME, 0, NOW), NOW)
    with pytest.raises(model.ControlError, match=message):
        control.follow(model.Target(q, sequence, stamp), stamp)
    assert not any(c[0] == "servo" for c in transport.calls)
    assert control.state == "fault"
    assert transport.calls[-1] == ("stop", True)


def test_valid_servo_then_halt_revokes_target_without_home():
    transport, control = setup()
    control.engage(model.Target(profile.HOME, 0, NOW), NOW)
    control.follow(
        model.Target(shifted(0.0005), 1, NOW + 20_000_000), NOW + 20_000_000
    )
    assert transport.calls[-1] == ("servo", shifted(0.0005))
    control.halt(NOW + 21_000_000)
    assert control.progress.target is None
    assert control.state == "stopping"
    assert transport.calls[-1] == ("stop", True)
    with pytest.raises(model.ControlError):
        control.follow(
            model.Target(profile.HOME, 2, NOW + 40_000_000), NOW + 40_000_000
        )
    assert not any(c[0] == "move" for c in transport.calls)


@pytest.mark.parametrize(
    "changes,now",
    [
        ({"q": shifted(6.0)}, NOW),
        ({"safety_mode": 3}, NOW),
        ({"runtime_state": 1}, NOW),
        ({"timestamp": 0.5}, NOW),
        ({}, NOW + 300_000_000),
    ],
)
def test_feedback_fault_withholds_watchdog(changes, now):
    transport, control = setup()
    transport.calls.clear()
    transport.feedback = dataclasses.replace(transport.feedback, **changes)
    with pytest.raises(model.ControlError):
        control.tick(now)
    assert ("heartbeat",) not in transport.calls
    assert control.state == "fault"


def test_stale_leader_with_fresh_feedback_still_faults():
    transport, control = setup()
    control.engage(model.Target(profile.HOME, 0, NOW), NOW)
    transport.feedback = dataclasses.replace(
        transport.feedback, timestamp=1.3, received_ns=NOW + 300_000_000
    )
    with pytest.raises(model.ControlError, match="leader input is stale"):
        control.tick(NOW + 300_000_000)


def test_unselected_source_cannot_engage_or_replace_leader():
    for engaged in (False, True):
        transport, control = setup()
        if engaged:
            control.engage(model.Target(profile.HOME, 0, NOW), NOW)
        call = control.follow if engaged else control.engage
        foreign = model.Target(profile.HOME, 1, NOW + 20_000_000, "dagger")
        with pytest.raises(model.ControlError, match="unauthorized"):
            call(foreign, NOW + 20_000_000)
        assert control.state == "fault"
        assert not any(c[0] in ("move", "servo") for c in transport.calls)
