"""Failures never leave unrecorded following or advance a queued key press."""

import contextlib
import dataclasses
import threading
import time

import pytest

from ur12e_collection.control import model, session
from ur12e_collection.simulation import profile, targets


class Transport:
    def __init__(self):
        self.sent = []
        self.stops = []
        self.closed = False

    def read(self):
        now = time.monotonic_ns()
        return model.State(
            profile.HOME,
            (0.0,) * 6,
            now / 1e9,
            now,
            currents=(0.0,) * 6,
            tcp=(0.0,) * 6,
        )

    def heartbeat(self):
        pass

    def servo(self, q):
        self.sent.append(q)

    def stop(self, servo):
        self.stops.append(servo)

    def close(self):
        self.closed = True


class Station:
    def __init__(self):
        self.transport = Transport()
        self.home_calls = 0

    @contextlib.contextmanager
    def motion(self):
        try:
            yield self.transport
        finally:
            self.transport.close()

    def read(self):
        return dataclasses.replace(self.transport.read(), runtime_state=1)

    def home(self):
        self.home_calls += 1
        raise AssertionError("unexpected HOME")


class Recorder:
    def __init__(self):
        self.abort = threading.Event()
        self.messages = []
        self.replies = []
        self.failure = None

    def send(self, kind, data=None):
        if kind == self.failure:
            raise RuntimeError("injected queue full")
        self.messages.append((kind, data))

    def poll(self):
        if self.failure == "poll":
            raise RuntimeError("injected dead recorder")
        replies, self.replies = self.replies, []
        return replies

    def close(self):
        self.abort.set()


def make(controlled, tmp_path):
    station, recorder = Station(), Recorder()
    owner = session.Session(
        station,
        recorder,
        session.Setup(
            profile.LIMITS,
            targets.Wave,
            controlled,
            tmp_path,
        ),
    )
    owner.lifecycle.state = "ready"
    owner.active.held = profile.HOME
    return owner, station, recorder


def test_no_servo_before_recorder_preparation(controlled, tmp_path):
    owner, station, recorder = make(controlled, tmp_path)
    owner.key(" ", time.monotonic_ns())
    for _ in range(5):
        owner.step()
    assert owner.state == "preparing"
    assert not station.transport.sent
    assert [kind for kind, _ in recorder.messages] == ["prepare"]
    recorder.replies = [("prepare", None)]
    owner.step()
    assert owner.state == "recording" and len(station.transport.sent) == 1
    owner.close()
    assert station.transport.stops == [True]
    assert not station.home_calls


@pytest.mark.parametrize("failure", ["prepare", "poll", "samples"])
def test_failed_recording_revokes_control(controlled, tmp_path, failure):
    owner, station, recorder = make(controlled, tmp_path)
    recorder.failure = failure
    with pytest.raises(RuntimeError):
        owner.key(" ", time.monotonic_ns())
        recorder.replies = [("prepare", None)]
        owner.step()
    assert owner.state == "fault"
    assert recorder.abort.is_set() and station.transport.closed
    assert not station.home_calls
    assert len(station.transport.sent) == (1 if failure == "samples" else 0)
    owner.close()


def test_held_feedback_stall_blocks_further_motion(
    controlled, tmp_path, monkeypatch
):
    owner, station, _ = make(controlled, tmp_path)
    state = station.read()
    monkeypatch.setattr(station, "read", lambda: state)
    monkeypatch.setattr(session.time, "monotonic_ns", lambda: state.received_ns)
    owner.step()
    monkeypatch.setattr(
        session.time, "monotonic_ns", lambda: state.received_ns + 300_000_000
    )
    with pytest.raises(model.ControlError, match="stale"):
        owner.step()
    assert owner.state == "fault" and not station.home_calls
    owner.close()
