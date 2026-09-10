"""Native-program ownership, measured arrival and failure behavior."""

import dataclasses

import pytest

from ur12e_collection.control import model, program
from ur12e_collection.simulation import profile


class Device:
    def __init__(self, monkeypatch):
        self.now = 1_000_000_000
        monkeypatch.setattr(program.time, "monotonic_ns", lambda: self.now)
        self.state = model.State(
            profile.HOME, (0.0,) * 6, 1.0, self.now, runtime_state=1
        )
        self.calls = []
        self.replies = {
            "running": "Program running: false",
            "load ready.urp": "Loading program: ready.urp",
            "play": "Starting program",
            "stop": "Stopped",
        }

    def command(self, command):
        self.calls.append(command)
        return self.replies[command]

    def read(self):
        return self.state

    def advance(self, **changes):
        self.now += 120_000_000
        self.state = dataclasses.replace(
            self.state,
            timestamp=self.state.timestamp + 0.12,
            received_ns=self.now,
            **changes,
        )

    def owner(self):
        return program.NativeHome(
            self.command, self.read, profile.LIMITS, "ready.urp"
        )


def test_play_is_not_arrival_and_handover_requires_measured_settle(monkeypatch):
    device = Device(monkeypatch)
    owner = device.owner()
    owner.start()
    assert owner.state == "moving"
    device.advance(runtime_state=2)
    owner.step()
    assert owner.state == "moving"
    device.advance(runtime_state=1)
    owner.step()
    device.advance()
    owner.step()
    assert owner.state == "hold"
    owner.close()
    assert "stop" not in device.calls


@pytest.mark.parametrize(
    "changes", [{"runtime_state": 2}, {"safety_mode": 3}, {"qd": (0.1,) * 6}]
)
def test_invalid_start_does_not_steal_program(monkeypatch, changes):
    device = Device(monkeypatch)
    device.state = dataclasses.replace(device.state, **changes)
    with pytest.raises(model.ControlError):
        device.owner().start()
    assert not device.calls


def test_native_program_ending_away_from_home_fails_and_stops(monkeypatch):
    device = Device(monkeypatch)
    device.state = dataclasses.replace(device.state, q=(1.0, *profile.HOME[1:]))
    owner = device.owner()
    owner.start()
    device.advance(runtime_state=2)
    owner.step()
    device.advance(runtime_state=1)
    with pytest.raises(model.ControlError, match="ended without arrival"):
        owner.step()
    assert owner.state == "fault"
    assert device.calls[-1] == "stop"


def test_stopped_program_may_hold_away_from_home(monkeypatch):
    device = Device(monkeypatch)
    device.state = dataclasses.replace(device.state, q=(1.0, *profile.HOME[1:]))
    owner = device.owner()
    owner.start()
    owner.stop()
    device.advance()
    owner.step()
    device.advance()
    owner.step()
    assert owner.state == "hold"
    assert owner.feedback.q[0] == 1.0


def test_stale_native_readback_requests_stop(monkeypatch):
    device = Device(monkeypatch)
    owner = device.owner()
    owner.start()
    device.now += 300_000_000
    with pytest.raises(model.ControlError, match="stale"):
        owner.step()
    assert device.calls[-1] == "stop"


def test_running_foreign_program_blocks_load(monkeypatch):
    device = Device(monkeypatch)
    device.replies["running"] = "Program running: true"
    with pytest.raises(model.ControlError, match="another native"):
        device.owner().start()
    assert device.calls == ["running"]
