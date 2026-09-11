"""Offline rejection, stop ownership and truthful hardware-diagnostic audits."""

import copy
import importlib.util
import io
import json
import math
import pathlib
import threading
import time
from unittest import mock
from types import SimpleNamespace

import pytest

from ur12e_collection.control import stop_audit as AUDIT


def _load(name):
    path = pathlib.Path(__file__).parent / "hardware" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


READY = _load("ready_interrupt")


@pytest.fixture(name="plan")
def plan_fixture():
    """A fresh explicitly simulated pose review."""
    return {
        "host": "fixture",
        "serial": "fixture",
        "environment": "ursim",
        "created_unix_ns": time.time_ns(),
        "initial_deg": [0, -90, -90, -90, 90, 10],
        "parameters": copy.deepcopy(READY.PARAMETERS),
    }


@pytest.mark.parametrize(
    "change", ["old", "rate", "nan", "wrap", "close", "bool"]
)
def test_invalid_plan_cannot_reach_control(plan, change):
    """Reject an expired review or altered numerical envelope."""
    if change == "old":
        plan["created_unix_ns"] -= 601_000_000_000
    elif change == "rate":
        plan["parameters"]["speed_deg_s"] = 2
    elif change == "bool":
        plan["parameters"]["speed_deg_s"] = True
    else:
        plan["initial_deg"][-1] = {"nan": math.nan, "wrap": 181, "close": 1}[
            change
        ]
    with pytest.raises(ValueError):
        READY.validate(plan)


def test_approval_precedes_any_file_or_network_access():
    """Unapproved execution must fail before any preflight IO."""
    with mock.patch.object(READY, "identity") as identity:
        with pytest.raises(ValueError, match="approval"):
            READY.execute(None, None, False)
    identity.assert_not_called()


def test_local_mode_allows_preparation_but_rejects_execution(plan):
    """Reading in Local mode does not authorize control."""
    result = {
        "state": "available",
        "responses": {
            "get serial number": "fixture",
            "is in remote control": "false",
            "safetystatus": "Safetystatus: NORMAL",
            "robotmode": "Robotmode: RUNNING",
        },
    }
    with mock.patch.object(READY.ur, "dashboard", return_value=result):
        READY.identity(plan, False)
        with pytest.raises(ValueError, match="Remote"):
            READY.identity(plan, True)


@pytest.mark.parametrize("accepted", [True, False])
def test_one_move_then_explicit_stop_even_if_move_rejected(accepted):
    """Stop the owned asynchronous movement without another target."""
    interrupted = threading.Event()
    control = mock.Mock()

    def move(*_):
        interrupted.set()
        return accepted

    control.moveJ.side_effect = move
    events = []
    if accepted:
        READY.drive(control, interrupted, events.append)
    else:
        with pytest.raises(RuntimeError, match="rejected"):
            READY.drive(control, interrupted, events.append)
    control.moveJ.assert_called_once_with(
        list(map(math.radians, READY.READY)),
        math.radians(1),
        math.radians(2),
        True,
    )
    control.stopJ.assert_called_once_with(math.radians(2), True)
    control.stopScript.assert_not_called()
    assert [e["event"] for e in events][-2:] == ["stop_request", "stop_ack"]


def test_cancel_before_move_sends_no_control():
    """An early signal cannot become a later movement."""
    interrupted = threading.Event()
    interrupted.set()
    control = mock.Mock()
    with pytest.raises(RuntimeError, match="before motion"):
        READY.drive(control, interrupted, lambda _: None)
    assert not control.mock_calls


@pytest.fixture(name="trace")
def trace_fixture(plan):
    """A complete synthetic motion, interruption and hold timeline."""

    def row(kind, seconds, **values):
        return {
            "event": kind,
            "monotonic_ns": round((100 + seconds) * 1e9),
            **values,
        }

    rows = [
        row(kind, seconds)
        for kind, seconds in (
            ("move_request", 0),
            ("move_ack", 0.001),
            ("sigint_handled", 2.015),
            ("stop_request", 2.02),
            ("stop_ack", 2.03),
            ("owner_finished", 2.9),
            ("observation_complete", 32.04),
        )
    ]
    rows.append(row("run_plan", -0.01, plan=plan))
    next(r for r in rows if r["event"] == "move_request")["parameters"] = plan[
        "parameters"
    ]
    next(r for r in rows if r["event"] == "stop_request")[
        "deceleration_deg_s2"
    ] = 2
    rows.append(row("sigint_sent", 2.01, reason="two_second_timer"))
    for index in range(3204):
        t = index / 100
        velocity = max(0, min(1, 1 - 2 * (t - 2.02)))
        rows.append(
            row(
                "feedback",
                t,
                source_s=t,
                q=list(
                    map(math.radians, [0, -90, -90, -90, 90, 10 - min(t, 2.52)])
                ),
                qd=[0] * 5 + [-math.radians(velocity)],
                runtime=2 if t < 2.9 else 1,
                safety=1,
                robot=7,
            )
        )
    return sorted(rows, key=lambda r: r["monotonic_ns"])


def test_audit_requires_motion_then_thirty_second_hold(trace):
    """A complete trace satisfies independent measured-state gates."""
    assert AUDIT.audit(trace)["state"] == "PASS"


@pytest.mark.parametrize(
    "failure", ["missing", "no_motion", "drift", "source", "fault", "short"]
)
def test_audit_rejects_false_stop_acceptance(trace, failure):
    """Incomplete or contradictory readback must not become acceptance."""
    if failure == "missing":
        trace[:] = [r for r in trace if r["event"] != "stop_request"]
    elif failure == "fault":
        trace.append({"event": "owner_error", "error": "fixture"})
    elif failure == "short":
        trace[:] = [r for r in trace if r["monotonic_ns"] < 131_000_000_000]
    else:
        samples = [r for r in trace if r["event"] == "feedback"]
        if failure == "no_motion":
            for r in samples:
                r["qd"] = [0] * 6
        elif failure == "drift":
            samples[-1]["q"] = [1] * 6
        else:
            samples[-1]["source_s"] = 0
    assert AUDIT.audit(trace)["state"] == "FAIL"


def test_stop_script_void_return_uses_readback_instead():
    """The pinned stopScript binding returns None after termination."""
    control = mock.Mock()
    control.stopScript.return_value = None
    events = []

    def sample(_):
        return SimpleNamespace(timestamp=time.monotonic(), qd=[0] * 6)

    with mock.patch.object(READY, "read_state", side_effect=sample):
        READY.finish_stop(control, None, events.append)
    control.stopScript.assert_called_once()
    assert events[-1]["event"] == "owner_finished"


def test_ten_second_review_requires_enough_remaining_travel(plan):
    """A longer timer cannot run against an already-nearby target."""
    plan["parameters"]["interrupt_after_s"] = 10
    with pytest.raises(ValueError, match="10.5"):
        READY.validate(plan)
    plan["initial_deg"][-1] = 12
    READY.validate(plan)


@pytest.mark.parametrize("delay", [2, 10])
def test_observer_signals_at_reviewed_delay_and_survives_thirty_seconds(delay):
    """Inject one SIGINT at the selected time without killing observation."""
    clock = [0.0]

    def now():
        clock[0] += 0.01
        return clock[0]

    def stamp(kind, **values):
        return {"event": kind, "monotonic_ns": round(clock[0] * 1e9), **values}

    channel = mock.Mock()
    channel.poll.side_effect = [True] + [False] * 10000
    channel.recv.return_value = {
        "event": "move_request",
        "monotonic_ns": 0,
        "parameters": {"interrupt_after_s": delay},
    }
    process = mock.Mock(pid=123)
    process.is_alive.return_value = True
    output = io.StringIO()
    with (
        mock.patch.object(READY.time, "monotonic", side_effect=now),
        mock.patch.object(READY.time, "sleep"),
        mock.patch.object(READY, "Observation") as observation,
        mock.patch.object(READY, "event", side_effect=stamp),
        mock.patch.object(READY.os, "kill") as kill,
    ):
        observation.return_value.sample.return_value = None
        READY.observe(None, process, channel, output, threading.Event())
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    sent = next(r for r in rows if r["event"] == "sigint_sent")
    assert delay <= sent["monotonic_ns"] / 1e9 <= delay + 0.1
    assert rows[-1]["monotonic_ns"] - sent["monotonic_ns"] >= 30_000_000_000
    kill.assert_called_once_with(123, READY.signal.SIGINT)


@pytest.mark.parametrize("failure", ["late", "resume", "gap", "cache"])
def test_settling_audit_rejects_late_or_false_confirmation(trace, failure):
    """Accept settling tails, but never resumed motion or discontinuous data."""
    samples = [r for r in trace if r["event"] == "feedback"]
    for r in samples:
        t = r["monotonic_ns"] / 1e9 - 100
        if failure == "late" and 2.52 <= t < 4:
            r["qd"][-1] = math.radians(0.02)
        elif failure == "resume" and 3 <= t < 3.1:
            r["qd"][-1] = math.radians(0.02)
        elif failure == "cache" and t >= 2.52:
            r["source_s"] = 2.52
    if failure == "gap":
        trace[:] = [
            r
            for r in trace
            if not 102_530_000_000 < r["monotonic_ns"] < 102_900_000_000
        ]
    assert AUDIT.audit(trace)["state"] == "FAIL"


def test_settling_tail_precedes_hold_measurement(trace):
    """A transient first crossing does not define the hold reference pose."""
    for r in trace:
        if (
            r["event"] == "feedback"
            and 102_600_000_000 <= r["monotonic_ns"] < 103_000_000_000
        ):
            r["qd"][-1] = math.radians(0.02)
    result = AUDIT.audit(trace)
    assert result["state"] == "PASS"
    assert result["policy"] == "settling-v2"
    assert result["metrics"]["stop_time_s"] == pytest.approx(1.18)


def test_audit_cli_never_overwrites_historical_results(trace, tmp_path):
    """Reassessment writes a distinct versioned file exactly once."""
    (tmp_path / "trace.jsonl").write_text("\n".join(map(json.dumps, trace)))
    original = tmp_path / "audit.json"
    original.write_text("historical FAIL")
    with pytest.raises(SystemExit) as result:
        AUDIT.main([str(tmp_path)])
    assert result.value.code == 0
    assert original.read_text() == "historical FAIL"
    with pytest.raises(FileExistsError):
        AUDIT.main([str(tmp_path)])
