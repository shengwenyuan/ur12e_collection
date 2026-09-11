"""Simulator preview stays separate from production recording acceptance."""

import contextlib
import json
from unittest import mock

import pytest

from ur12e_collection.leader import episode
from ur12e_collection.simulation import live_leader, rehearsal
from test_control_session import Station
from test_leader_episode import calibration


class Source:
    def __init__(self):
        self.calibration = calibration()
        self.origin = {"kind": "test"}
        self.failure = None
        self.moving = False
        self.view = None

    def samples(self, now):
        if self.failure:
            raise self.failure
        if self.view is not None:
            return self.view
        self.view = tuple(
            episode.Sample(
                "test",
                i,
                now - (4 - i) * 20_000_000,
                now - (4 - i) * 20_000_000 + 1_000_000,
                (2200 + (i * 5 if self.moving else 0),) * 7,
            )
            for i in range(4)
        )
        return self.view


def test_idle_expiry_recovers_without_acquiring_motion():
    station, source = Station(), Source()
    preview = rehearsal.Preview(station, source)
    source.failure = live_leader.Unavailable("expired")
    preview.step()
    preview.state = "ready"
    preview.key(" ")
    assert preview.state == "ready" and preview.program is None
    source.failure = None
    preview.step()
    assert preview.state == "ready" and not station.transport.sent
    preview.close()


def test_moving_start_waits_before_acquiring_sdk():
    source = Source()
    source.moving = True
    station = Station()
    station.motion = mock.Mock(side_effect=AssertionError("SDK acquired"))
    preview = rehearsal.Preview(station, source)
    preview.state = "ready"
    preview.key(" ")
    station.motion.assert_not_called()
    assert preview.state == "ready"


def test_following_expiry_stops_and_never_auto_resumes():
    station, source = Station(), Source()
    preview = rehearsal.Preview(station, source)
    preview.state = "ready"
    preview.key(" ")
    assert preview.state == "following"
    source.failure = live_leader.Unavailable("expired")
    preview.step()
    assert preview.state == "stopping" and station.transport.stops == [True]
    source.failure = None
    preview.program.progress.state = "hold"
    preview.step()
    preview.step()
    assert preview.state == "held"
    assert not station.transport.sent and station.home_calls == 0
    preview.close()


def test_close_while_following_stops_without_home():
    station = Station()
    preview = rehearsal.Preview(station, Source())
    preview.state = "ready"
    preview.key(" ")
    preview.close()
    assert station.transport.stops == [True]
    assert station.home_calls == 0


def test_hard_source_fault_is_not_treated_as_expiry():
    source = Source()
    preview = rehearsal.Preview(Station(), source)
    source.failure = ValueError("epoch changed")
    with pytest.raises(ValueError, match="epoch"):
        preview.step()
    preview.close()


def test_run_fault_stops_and_preserves_report(tmp_path, monkeypatch):
    station, source = Station(), Source()
    source.failure = ValueError("lost live source")
    monkeypatch.setattr(
        rehearsal.console,
        "keyboard",
        lambda _: contextlib.nullcontext(lambda: []),
    )
    monkeypatch.setattr(
        rehearsal.live_leader,
        "Live",
        lambda *_: contextlib.nullcontext(source),
    )
    monkeypatch.setattr(
        rehearsal.connection,
        "open_station",
        lambda: contextlib.nullcontext(station),
    )
    original = rehearsal.pathlib.Path.read_text
    monkeypatch.setattr(
        rehearsal.pathlib.Path,
        "read_text",
        lambda path, *args, **kwargs: (
            '{"source_revision": "test"}'
            if str(path) == "/sim-permit.json"
            else original(path, *args, **kwargs)
        ),
    )
    output = tmp_path / "preview"
    with pytest.raises(ValueError, match="lost live source"):
        rehearsal.run(output, "test", None, (None, None))
    report = json.loads((output / "rehearsal.json").read_text())
    assert report["state"] == "failed" and not report["recording"]
    assert report["commands"] == 0
    assert list(output.iterdir()) == [output / "rehearsal.json"]


def test_relative_trend_and_no_initial_jump(monkeypatch):
    now = [1_000_000_000]
    monkeypatch.setattr(rehearsal.time, "monotonic_ns", lambda: now[0])
    station, source = Station(), Source()
    preview = rehearsal.Preview(station, source)
    preview.state = "ready"
    preview.key(" ")
    assert preview.program.progress.target.q == rehearsal.profile.HOME
    now[0] += 20_000_000
    source.view += (
        episode.Sample(
            "test",
            4,
            now[0] - 2_000_000,
            now[0] - 1_000_000,
            (2210,) * 7,
        ),
    )
    preview.step()
    q = station.transport.sent[-1]
    assert q[0] > rehearsal.profile.HOME[0]
    assert q[1] < rehearsal.profile.HOME[1]
    preview.key(" ")
    assert station.transport.stops == [True]
    preview.program.progress.state = "hold"
    preview.close()
