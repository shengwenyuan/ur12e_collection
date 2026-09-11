"""Live rehearsal preserves physical source timing and no-write boundaries."""

import dataclasses

import pytest

from ur12e_collection.control import model
from ur12e_collection.simulation import bridge, live_leader
from ur12e_collection.leader import input as leader_input
from test_leader_episode import calibration, sample, HOME


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(live_leader.time, "monotonic_ns", lambda: 41_000_000)
    path = tmp_path / "calibration.json"
    calibration().save(path)
    monkeypatch.setattr(
        bridge.Clock,
        "synchronize",
        lambda self: setattr(self, "bounds", (0, 0)),
    )
    monkeypatch.setattr(bridge.Clock, "check", lambda *_: None)
    value = live_leader.Feed(tmp_path, path)
    data = dict(
        epoch="serial-session-1",
        published_ns=41_000_000,
        health_start_ns=0,
        health_end_ns=1_000_000,
        torque=[0] * 7,
        hardware_error=[0] * 7,
        health_errors=[0] * 7,
        samples=[dataclasses.asdict(sample(i)) for i in range(3)],
    )
    bridge.write(tmp_path / "latest.json", data)
    return value, data


def test_clock_bound_is_conservative_and_rejects_unbounded_delay():
    assert bridge.bracket(100, 1000, 105) == (-900, -895)
    with pytest.raises(ValueError, match="25 ms"):
        bridge.bracket(0, 0, 25_000_001)
    with pytest.raises(ValueError):
        bridge.bracket(True, 0, 1)
    with pytest.raises(ValueError):
        bridge.bracket(2, 0, 1)


def test_nonce_reply_cannot_be_replayed(tmp_path):
    clock = bridge.Clock(tmp_path)
    clock.request(100)
    bridge.write(
        tmp_path / "clock-reply.json",
        {"nonce": "old", "request_ns": 100, "host_ns": 1000},
    )
    assert clock.receive(101) is None
    with pytest.raises(ValueError, match="expired"):
        clock.receive(25_000_101)
    request = bridge.read(tmp_path / "clock-request.json")
    bridge.write(tmp_path / "clock-reply.json", request | {"host_ns": 1000})
    assert clock.receive(105) == (-900, -895)


def test_bridge_rejects_large_or_nonobject_messages(tmp_path):
    path = tmp_path / "value.json"
    path.write_text("x" * 262145)
    with pytest.raises(ValueError, match="large"):
        bridge.read(path)
    path.write_text("[]")
    with pytest.raises(ValueError, match="object"):
        bridge.read(path)


def test_cached_source_keeps_acquisition_time_and_expires(live):
    value, _ = live
    first = value.samples(41_000_000)
    assert value.samples(51_000_000) == first
    assert first[-1].start_ns == 40_000_000
    with pytest.raises(ValueError, match="stale"):
        value.samples(141_000_001)


@pytest.mark.parametrize(
    "fault",
    [
        "torque",
        "hardware_error",
        "health_errors",
        "epoch",
        "future",
        "health",
        "publisher",
        "counter",
        "mutated",
        "acquisition",
    ],
)
def test_bad_live_input_cannot_drive_a_session(live, fault):
    value, data = live
    value.samples(41_000_000)
    if fault in ("torque", "hardware_error", "health_errors"):
        data[fault][0] = 1
    elif fault == "epoch":
        data["epoch"] = "restarted"
    elif fault == "future":
        data["published_ns"] = 200_000_000
    elif fault == "health":
        data["health_end_ns"] = 200_000_000
    elif fault == "publisher":
        data["fault"] = "closed"
    elif fault == "counter":
        data["samples"] = data["samples"][:-1]
    elif fault == "mutated":
        raw = data["samples"][-1]["raw"]
        data["samples"][-1]["raw"] = (raw[0] + 1, *raw[1:])
    else:
        data["samples"].append(dataclasses.asdict(sample(4)))
    bridge.write(value.root / "latest.json", data)
    with pytest.raises(ValueError):
        value.samples(61_000_000)


def test_live_input_uses_shared_relative_conditioning(live):
    value, data = live
    limits = model.Limits((-6.0,) * 6, (6.0,) * 6, HOME)
    follower = model.State(HOME, (0.0,) * 6, 1.0, 41_000_000)
    active = leader_input.Input(
        value, value.calibration, limits, follower, 41_000_000
    )
    assert active.sample(41_000_000).q == HOME
    data["samples"].append(dataclasses.asdict(sample(3, raw=2210)))
    data["published_ns"] = 61_000_000
    bridge.write(value.root / "latest.json", data)
    result = active.sample(61_000_000)
    assert result.q[0] > HOME[0] and result.q[1] < HOME[1]
    assert active.evidence()["sequence"] == 3
    assert active.context()["input_origin"]["kind"] == "physical_live_leader"


def test_120hz_startup_retains_more_than_four_samples(live):
    value, data = live
    data["samples"] = [
        dataclasses.asdict(
            dataclasses.replace(
                sample(i),
                start_ns=i * 8_333_333,
                end_ns=i * 8_333_333 + 1_000_000,
            )
        )
        for i in range(7)
    ]
    data["published_ns"] = 51_000_000
    bridge.write(value.root / "latest.json", data)
    limits = model.Limits((-6.0,) * 6, (6.0,) * 6, HOME)
    active = leader_input.Input(
        value,
        value.calibration,
        limits,
        model.State(HOME, (0.0,) * 6, 1.0, 51_000_000),
        51_000_000,
    )
    assert active.sample(51_000_000).q == HOME


def test_export_command_is_not_available():
    from ur12e_collection import cli

    with pytest.raises(SystemExit):
        cli.parser().parse_args(["episode", "export"])


def test_publish_during_read_is_deferred_without_retiming(live, monkeypatch):
    value, data = live
    data["samples"].append(dataclasses.asdict(sample(3)))
    data["published_ns"] = 61_000_000
    bridge.write(value.root / "latest.json", data)
    monkeypatch.setattr(live_leader.time, "monotonic_ns", lambda: 62_000_000)
    assert value.samples(60_000_000)[-1].sequence == 2
    latest = value.samples(63_000_000)[-1]
    assert latest.sequence == 3 and latest.start_ns == 60_000_000


def test_periodic_clock_discontinuity_is_rejected(tmp_path, monkeypatch):
    clock = bridge.Clock(tmp_path)
    clock.bounds = (10, 15)
    clock.pending = ("nonce", 0)
    monkeypatch.setattr(clock, "receive", lambda **_: (16, 20))
    with pytest.raises(ValueError, match="alignment changed"):
        clock.check(1)


def test_fixed_size_publication_and_writer_size_limit(tmp_path):
    path = tmp_path / "message.json"
    bridge.write(path, {"v": "a"})
    assert path.stat().st_size == bridge.MESSAGE_BYTES
    bridge.write(path, {"v": "b" * 1000})
    assert path.stat().st_size == bridge.MESSAGE_BYTES
    assert bridge.read(path) == {"v": "b" * 1000}
    with pytest.raises(ValueError, match="too large"):
        bridge.write(path, {"v": "x" * bridge.MESSAGE_BYTES})
    assert bridge.read(path) == {"v": "b" * 1000}
    assert not tuple(tmp_path.glob("*.tmp"))


def test_worker_reports_failure_and_closes_bounded_channel(monkeypatch):
    import queue
    from unittest import mock

    feed = mock.Mock(origin={"kind": "fixture"})
    feed.samples.side_effect = [(sample(0),), ValueError("source loss")]
    monkeypatch.setattr(live_leader, "Feed", lambda *_: feed)
    samples = mock.Mock()
    samples.get_nowait.side_effect = queue.Empty
    samples.put_nowait.side_effect = queue.Full
    status, stop = mock.Mock(), mock.Mock()
    stop.is_set.return_value = False
    live_leader._receive(None, None, samples, status, stop)
    assert status.send.call_args_list == [
        mock.call(("ready", {"kind": "fixture"})),
        mock.call(("error", "source loss")),
    ]
    samples.cancel_join_thread.assert_called_once()
    samples.close.assert_called_once()
    status.close.assert_called_once()


def test_live_console_fault_closes_owner_and_preserves_failed_report(
    tmp_path, monkeypatch
):
    import contextlib
    import json
    from unittest import mock
    from ur12e_collection.simulation import session

    live = mock.Mock()
    live.samples.side_effect = ValueError("lost live source")
    monkeypatch.setattr(
        live_leader, "Live", lambda *_: contextlib.nullcontext(live)
    )
    monkeypatch.setattr(
        session.console,
        "keyboard",
        lambda _: contextlib.nullcontext(lambda: []),
    )
    monkeypatch.setattr(
        session.connection,
        "open_station",
        lambda: contextlib.nullcontext(mock.Mock()),
    )
    owner = mock.Mock(
        state="recording", timings=[], observer=None, completed=[]
    )
    owner.snapshot = {"control": {"control_hz": 120}}
    monkeypatch.setattr(session, "create", lambda *_, **__: owner)
    output = tmp_path / "console"
    with pytest.raises(ValueError, match="lost live source"):
        session.run(output, "test", None, live_config=(None, None))
    owner.close.assert_called_once()
    owner.step.assert_not_called()
    report = json.loads((output / "session.json").read_text())
    assert report["state"] == "failed"
    assert report["error"] == "ValueError: lost live source"
