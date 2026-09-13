"""Protective stops retire control while capture and read-only review survive."""

import dataclasses
import time
from types import SimpleNamespace
from unittest import mock

import pytest

from ur12e_collection import contracts, recording, session, storage
from ur12e_collection.control import collection, model, owner as motion_owner
from ur12e_collection.physical import transport
from test_collection import owner, recording as begin_recording, hande
from test_control_records import samples
from test_physical_teleop import configuration
from test_recording import Source


def observed(stamp, *, speed=0.0, source=None):
    return contracts.URFeedback(
        contracts.Provenance(
            "fixture",
            stamp,
            contracts.SampleTime(
                stamp if source is None else source,
                "ur_controller_uptime",
                stamp,
            ),
            True,
        ),
        (0.0,) * 6,
        (speed,) * 6,
        (0.0,) * 6,
        (0.0,) * 6,
        7,
        3,
    )


@pytest.mark.parametrize("runtime", [3, 4, 1])
def test_protected_transport_retains_fault_and_closes_without_sdk_writes(
    monkeypatch, runtime
):
    clock = [1_000_000_000]
    monkeypatch.setattr(transport.time, "monotonic_ns", lambda: clock[0])
    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0] / 1e9)
    monkeypatch.setattr(
        transport.time,
        "sleep",
        lambda dt: clock.__setitem__(0, clock[0] + round(dt * 1e9)),
    )
    config = configuration()
    state = lambda: model.State(
        config["limits"].ready,
        (0.0,) * 6,
        clock[0] / 1e9,
        clock[0],
        7,
        3,
        runtime,
    )
    monkeypatch.setattr(transport, "read_state", lambda _: state())
    sdk, receiver, tool, log = (mock.Mock() for _ in range(4))
    sdk.isProgramRunning.return_value = False
    sdk.isConnected.return_value = False
    tool.view.return_value = SimpleNamespace(
        registers=(("POS", 0), ("OBJ", 3)), acquired_ns=clock[0]
    )
    device = transport.Transport(sdk, receiver, tool, config, emit=log)
    device.watchdog_enabled = True
    controller = motion_owner.Controller(device, config["limits"])
    controller.progress.state = "following"
    with pytest.raises(
        model.ControlError, match=f"safety=3, runtime={runtime}"
    ):
        controller.tick(clock[0])
    assert controller.progress.feedback.safety_mode == 3
    assert controller.progress.state == "fault"
    assert device.protected and device.halted
    controller.close()
    assert sdk.mock_calls == [mock.call.disconnect()]
    tool.hold.assert_called()
    tool.offer.assert_not_called()
    tool.view.assert_not_called()
    receiver.disconnect.assert_called_once()
    assert {c.args[0] for c in log.call_args_list} >= {
        "protective_stop",
        "standstill_confirmed",
        "protective_stop_confirmed",
    }


@pytest.mark.parametrize("mode", ["moving", "stale"])
def test_protected_cleanup_cannot_claim_unobserved_standstill(
    monkeypatch, mode
):
    clock = [1_000_000_000]
    monkeypatch.setattr(transport.time, "monotonic_ns", lambda: clock[0])
    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0] / 1e9)
    monkeypatch.setattr(
        transport.time,
        "sleep",
        lambda dt: clock.__setitem__(0, clock[0] + round(dt * 1e9)),
    )
    config = configuration()
    monkeypatch.setattr(
        transport,
        "read_state",
        lambda _: model.State(
            config["limits"].ready,
            ((0.1 if mode == "moving" else 0.0),) * 6,
            1.0 if mode == "stale" else clock[0] / 1e9,
            clock[0],
            7,
            3,
            4,
        ),
    )
    sdk, receiver, tool = mock.Mock(), mock.Mock(), mock.Mock()
    device = transport.Transport(sdk, receiver, tool, config)
    with pytest.raises(model.ControlError, match="stop unconfirmed"):
        device.close()
    assert sdk.mock_calls == [mock.call.disconnect()]
    assert device.closed


def test_independent_stop_observation_rejects_stale_or_moving_feedback():
    rejection = collection.Rejection("protected")
    for stamp in range(1_000_000_000, 1_300_000_001, 10_000_000):
        rejection.observe([observed(stamp)], stamp)
    assert rejection.stopped_ns
    rejection.observe([], 1_600_000_000)
    assert not rejection.stopped_ns
    for stamp in range(1_700_000_000, 2_000_000_001, 10_000_000):
        rejection.observe([observed(stamp, source=1_700_000_000)], stamp)
    assert not rejection.stopped_ns
    rejection.observe([observed(2_100_000_000, speed=0.01)], 2_100_000_000)
    assert not rejection.stopped_ns


@pytest.mark.parametrize("choice", [" ", "a", "q"])
def test_protective_review_saves_or_discards_and_requires_new_session(
    owner, monkeypatch, choice
):
    begin_recording(owner)
    clock = [2_000_000_000]
    monkeypatch.setattr(collection.time, "monotonic_ns", lambda: clock[0])
    owner.motion.reject.side_effect = lambda *_: setattr(
        owner.motion, "state", "blocked"
    )
    owner.motion.step.side_effect = model.ControlError("safety=3, runtime=3")
    owner.step(clock[0])
    owner.motion.step.side_effect = None
    assert owner.phase == "review"
    assert (
        mock.call("freeze", 2_000_000_000) in owner.recorder.send.call_args_list
    )
    for stamp in range(2_010_000_000, 2_310_000_001, 10_000_000):
        clock[0] = stamp
        owner.readers.read.return_value = [observed(stamp), hande(stamp)]
        owner.step(stamp)
    assert owner.active.stop_sent and owner.active.settled_ns
    assert owner.fault_feedback[0].safety_mode == 3
    owner.readers.read.return_value = []
    owner.key(choice, 3_000_000_000)
    owner.step(clock[0])
    if choice == "a":
        assert owner.phase == "cancelling"
        owner.recorder.poll.return_value = [("cancelled", {})]
    else:
        assert owner.phase == "finalizing"
        owner.active.path.mkdir()
        owner.recorder.poll.return_value = [
            ("complete", {"episode": "episode-0000"})
        ]
    owner.step(clock[0])
    assert owner.phase == "blocked"
    assert owner.done == (choice == "q")
    owner.motion.key.reset_mock()
    owner.key(" ", 4_000_000_000)
    owner.motion.key.assert_not_called()
    owner.motion.close.assert_not_called()
    owner.recorder.abort.set.assert_not_called()


@pytest.mark.parametrize("tail", [True, False])
def test_frozen_capture_survives_35_seconds_of_three_camera_input(
    tmp_path, controlled, group_factory, frame_factory, tail
):
    """Advance a virtual 30-Hz scene through the actual capture and codec writer."""
    disk = session.Session.from_snapshot(controlled)
    source = Source()
    capture = recording._Capture(source, disk)
    data = samples(controlled)
    try:
        path = tmp_path / "episode"
        capture.message("prepare", str(path))
        capture.message("begin", (0, data[0]))
        source.frames = list(group_factory().members)
        capture.message("samples", (4_000_000, data[1:-1]))
        capture.step(5_000_000)
        capture.message("freeze", 40_000_000)
        if tail:
            event = dataclasses.replace(data[-1], reason="rejected: safety=3")
            capture.message("stop", (40_000_000, event))
        for index in range(1, 1051):
            stamp = 40_000_000 + index * 33_333_333
            source.frames = [
                frame_factory(role, stamp, index)
                for role in contracts.CAMERA_ROLES
            ]
            assert capture.step(stamp) is None
            assert not capture.pending
            assert disk.state == "recording"
        if tail:
            capture.message("settled", None)
        else:
            capture.message("cancel", None)
        result = None
        deadline = time.monotonic() + 5
        while result is None and time.monotonic() < deadline:
            result = capture.step(stamp + 100_000_000)
            time.sleep(0.005)
        assert result is not None
        if tail:
            assert (
                storage.verify_episode(path)["counts"]["camera/frame_set"] == 1
            )
        else:
            assert result["cancelled"] and not path.exists()
        assert capture.source is source
        capture.message("prepare", str(tmp_path / "next"))
        assert disk.state == "prepared"
    finally:
        disk.close()
