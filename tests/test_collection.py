"""Recording ownership, stop boundaries and session teardown without hardware."""

import json
from unittest import mock

import pytest

from ur12e_collection import contracts
from ur12e_collection.control import collection, records
from ur12e_collection.leader import mapping
from test_leader_input import make


def hande(stamp, sequence=0):
    return contracts.HandEFeedback(
        contracts.Provenance(
            "test-hande",
            sequence,
            contracts.SampleTime(None, "unavailable", stamp),
            True,
        ),
        (
            ("POS", 12),
            ("PRE", 13),
            ("STA", 3),
            ("OBJ", 0),
            ("FLT", 0),
            ("COU", 0),
        ),
        stamp - 1,
    )


@pytest.fixture
def owner(tmp_path, controlled):
    controlled["control"].update(hande="urcap", hande_id="test-hande")
    motion, recorder, readers = mock.Mock(), mock.Mock(), mock.Mock()
    motion.state = "ready"
    motion.reject.side_effect = lambda *_: setattr(motion, "state", "stopping")
    motion.last_key_ns = 1_000_000_000
    recorder.poll.return_value = []
    readers.read.return_value = []
    return collection.Session(motion, recorder, readers, controlled, tmp_path)


def prepare(owner):
    owner.key(" ", 1_000_000_000)
    assert owner.state == "preparing"
    owner.recorder.poll.return_value = [("prepare", None)]
    owner.step(1_100_000_000)
    owner.recorder.poll.return_value = []


def recording(owner):
    prepare(owner)
    owner.phase = "recording"
    owner.motion.state = "following"
    owner.active.start = 1_100_000_000


def test_writer_readiness_precedes_engagement_and_retry(owner):
    owner.key(" ", 1_000_000_000)
    owner.motion.key.assert_not_called()
    owner.recorder.poll.return_value = [("prepare", None)]
    owner.motion.state = "waiting_leader"
    owner.step(1_100_000_000)
    assert owner.phase == "engaging"
    owner.recorder.poll.return_value = []
    owner.step(1_200_000_000)
    assert owner.phase == "engaging"
    assert not any(
        c.args[0] == "begin" for c in owner.recorder.send.call_args_list
    )


def test_stop_dispatch_precedes_ipc_and_tail_waits_for_both_sources(owner):
    recording(owner)
    calls = []

    def stop(_now):
        calls.append("stop")
        owner.motion.state = "stopping"

    owner.motion.stop.side_effect = stop
    owner.recorder.send.side_effect = lambda op, *args: calls.append(op)
    owner.key(" ", 2_000_000_000)
    assert calls == ["stop"]
    owner.readers.read.return_value = [hande(1_999_999_999)]
    owner.receipts["ur_feedback"] = 2_000_000_001
    owner.step(2_001_000_000)
    assert calls == ["stop"]
    owner.readers.read.return_value = [hande(2_000_000_002, 1)]
    owner.motion.state = "held"
    owner.step(2_010_000_000)
    assert calls == ["stop", "samples", "stop", "settled"]
    messages = owner.recorder.send.call_args_list
    cutoff, samples = next(
        c.args[1] for c in messages if c.args[0] == "samples"
    )
    assert cutoff == 2_000_000_000
    assert len(samples) == 1
    assert samples[0].provenance.time.received_monotonic_ns < cutoff
    assert owner.state == "finalizing"
    owner.key(" ", 3_000_000_000)
    assert owner.state == "finalizing"


def test_completed_episode_allows_new_home_without_restarting_resources(owner):
    recording(owner)
    owner.active.path.mkdir()
    owner.phase = "finalizing"
    owner.motion.state = "held"
    owner.recorder.poll.return_value = [
        ("complete", {"episode": "episode-0000"})
    ]
    owner.step(2_000_000_000)
    owner.key(" ", 3_000_000_000)
    owner.motion.key.assert_called_with(" ", 3_000_000_000)
    owner.motion.state = "ready"
    owner.key(" ", 4_000_000_000)
    assert owner.active.path.name == "episode-0001"
    owner.recorder.start.assert_not_called()
    owner.readers.start.assert_not_called()
    report = json.loads((owner.output / "session.json").read_text())
    assert report["episodes"][0]["disposition"] == "retained"


@pytest.mark.parametrize(
    "phase", ["preparing", "engaging", "finalizing", "idle"]
)
def test_normal_quit_waits_only_for_started_episode(owner, phase):
    prepare(owner)
    owner.phase = phase
    if phase == "idle":
        owner.active = None
    owner.motion.state = "ready"
    owner.key("q", 1_101_000_000)
    assert owner.done == (phase != "finalizing")
    if owner.done:
        owner.close()
        assert (
            json.loads((owner.output / "session.json").read_text())["state"]
            == "complete"
        )
        owner.readers.request_stop.assert_called_once()


def test_quit_bypasses_debounce_and_drains_active_episode(owner):
    recording(owner)
    owner.last_key = 2_000_000_000
    owner.motion.stop.side_effect = lambda _: setattr(
        owner.motion, "state", "stopping"
    )
    owner.key("q", 2_000_000_001)
    owner.motion.stop.assert_called_once()
    assert not owner.done
    assert owner.active.reason == "session_end"


@pytest.mark.parametrize("fault", ["recorder", "readers"])
def test_required_io_failure_keeps_operator_choices_and_blocks_restart(
    owner, fault
):
    recording(owner)
    operation = (
        owner.recorder.poll if fault == "recorder" else owner.readers.read
    )
    operation.reset_mock()
    operation.side_effect = RuntimeError("lost")
    owner.step(2_000_000_000)
    assert owner.phase == "review"
    assert fault in owner.rejection.unavailable
    owner.motion.reject.assert_called_once()
    owner.motion.close.assert_not_called()
    owner.key(" ", 3_000_000_000)
    owner.step(3_000_000_000)
    assert owner.phase == "review"  # A save cannot certify broken data.
    owner.key("q", 3_000_000_001)
    owner.step(3_010_000_000)
    if fault == "readers":
        assert owner.phase == "cancelling"
        owner.recorder.poll.return_value = [("cancelled", {})]
        owner.step(3_020_000_000)
        owner.recorder.poll.return_value = []
    owner.motion.state = "held"
    owner.step(3_100_000_000)
    assert owner.phase == "blocked" and owner.done
    assert owner.completed[0]["verified"] is False
    assert owner.completed[0]["disposition"] == "incomplete"
    operation.assert_called_once()
    owner.motion.close.assert_not_called()
    owner.close()
    owner.motion.close.assert_called_once()


def test_real_raw_mapping_and_separate_sent_arm_command(owner, monkeypatch):
    source, active = make()
    owner.snapshot["control"]["leader_id"] = "gello"
    owner.active = collection.Episode(
        owner.output / "episode-0000",
        records.Records(owner.snapshot["control"], simulated=True),
    )
    owner.motion.input = active
    owner.motion.gripper_reference = mapping.GripperReference(3200, 1)
    active.sample(41_000_000)
    owner._begin()
    target = active.sample(61_000_000)
    owner.motion.controller.progress.target = target
    monkeypatch.setattr(collection.time, "monotonic_ns", lambda: 62_000_000)
    owner._samples([hande(61_500_000)])
    _, samples = owner.recorder.send.call_args.args[1]
    intent, command, observed = samples
    assert intent.acquisition["raw"] == source.rows[-1].raw
    assert intent.gripper_request_raw == 0
    assert command.gripper_request_raw is None
    assert observed.registers[0] == ("POS", 12)


def test_discard_then_normal_quit_commits_explicit_outcome(owner):
    recording(owner)
    owner.active.path.mkdir()
    owner.motion.stop.side_effect = lambda _: setattr(
        owner.motion, "state", "stopping"
    )
    owner.key("a", 2_000_000_000)
    assert owner.active.discard and owner.active.reason == "discard"
    owner.phase = "finalizing"
    owner.motion.state = "held"
    owner.key("q", 2_000_000_001)
    assert not owner.done
    owner.recorder.poll.return_value = [
        ("complete", {"episode": "episode-0000"})
    ]
    owner.step(3_000_000_000)
    assert owner.done
    outcome = json.loads(
        (owner.output / "episode-0000/outcome.json").read_text()
    )
    assert outcome["disposition"] == "discarded"
    assert outcome["task_success"] is None
    owner.close()
    assert (
        json.loads((owner.output / "session.json").read_text())["state"]
        == "complete"
    )


def test_failed_writer_preparation_never_engages_motion(owner):
    owner.recorder.send.side_effect = RuntimeError(
        "recording command queue overflow"
    )
    owner.key(" ", 1_000_000_000)
    assert owner.phase == "review"
    owner.motion.key.assert_not_called()
    owner.motion.close.assert_not_called()
    owner.key("q", 1_100_000_000)
    owner.step(1_200_000_000)  # Cancellation discovers the broken IPC channel.
    owner.motion.state = "held"
    owner.step(1_300_000_000)
    owner.step(1_400_000_000)
    assert owner.done
    assert owner.completed[0]["verified"] is False


def reject_input(owner, monkeypatch):
    recording(owner)
    monkeypatch.setattr(collection.time, "monotonic_ns", lambda: 2_000_000_000)
    owner.motion.step.side_effect = ValueError("input jump")
    owner.step(2_000_000_000)
    owner.motion.step.side_effect = None
    assert owner.phase == "review"
    assert owner.active.cutoff == 2_000_000_000
    assert not owner.rejection.unavailable


@pytest.mark.parametrize("choice", [" ", "a", "q"])
def test_rejection_choices_wait_for_stop_and_writer_without_early_cleanup(
    owner, monkeypatch, choice
):
    reject_input(owner, monkeypatch)
    owner.key(choice, 3_000_000_000)
    owner.step(3_000_000_000)
    owner.motion.close.assert_not_called()
    owner.motion.key.reset_mock()
    if choice == "a":
        assert owner.phase == "cancelling"
        owner.recorder.poll.return_value = [("cancelled", {})]
        owner.step(3_010_000_000)
        owner.recorder.poll.return_value = []
        assert owner.phase == "resolving"  # Writer closed; arm still stopping.
    else:
        assert owner.phase == "review"
        assert not any(
            c.args[0] == "settled" for c in owner.recorder.send.call_args_list
        )
    owner.motion.state = "held"
    owner.receipts.update(
        ur_feedback=3_100_000_000, hande_feedback=3_100_000_000
    )
    owner.step(3_100_000_000)
    if choice != "a":
        assert owner.phase == "finalizing"
        owner.active.path.mkdir()
        owner.recorder.poll.return_value = [
            ("complete", {"episode": "episode-0000"})
        ]
        owner.step(3_200_000_000)
        owner.recorder.poll.return_value = []
        outcome = json.loads(
            (owner.output / "episode-0000/outcome.json").read_text()
        )
        assert outcome["interruption"] == "input jump"
        assert (
            owner.completed[0]["stop_confirmed_monotonic_ns"] == 3_100_000_000
        )
    else:
        assert owner.completed[0]["disposition"] == "discarded"
        assert owner.completed[0]["verified"] is False
    assert owner.phase == "idle" and owner.rejection is None
    assert owner.done == (choice == "q")
    owner.motion.key.assert_not_called()
    owner.recorder.start.assert_not_called()
    owner.readers.start.assert_not_called()
    if choice != "q":
        owner.key(" ", 4_000_000_000)
        owner.motion.key.assert_called_once_with(" ", 4_000_000_000)
        owner.motion.state = "ready"
        owner.key(" ", 5_000_000_000)
        assert owner.active.path.name == "episode-0001"


def test_failed_stop_still_allows_quit_without_certifying_episode(
    owner, monkeypatch
):
    reject_input(owner, monkeypatch)
    owner.motion.step.side_effect = ValueError("stop timed out")
    owner.step(3_000_000_000)
    owner.motion.controller.fail.assert_called_once_with("stop timed out")
    owner.key("q", 3_100_000_000)
    monkeypatch.setattr(collection.time, "monotonic_ns", lambda: 4_100_000_000)
    owner.step(4_100_000_000)
    assert owner.phase == "cancelling"
    owner.recorder.poll.return_value = [("cancelled", {})]
    owner.step(3_300_000_000)
    assert owner.done and owner.phase == "blocked"
    assert owner.completed[0]["verified"] is False
    owner.motion.close.assert_not_called()


def test_fault_during_finalization_allows_disposition_and_quit(owner):
    recording(owner)
    owner.active.path.mkdir()
    owner.phase = "finalizing"
    owner.motion.state = "held"
    owner.motion.step.side_effect = ValueError("leader disconnected")
    owner.step(2_000_000_000)
    owner.motion.step.side_effect = None
    owner.motion.state = "held"
    owner.key("a", 3_000_000_000)
    owner.key("q", 3_100_000_000)
    owner.recorder.poll.return_value = [
        ("complete", {"episode": "episode-0000"})
    ]
    owner.step(3_200_000_000)
    assert owner.done
    assert owner.completed[0]["disposition"] == "discarded"


@pytest.mark.parametrize("choice", ["a", "q"])
def test_existing_exit_or_discard_intent_survives_late_rejection(owner, choice):
    recording(owner)
    owner.motion.stop.side_effect = lambda _: setattr(
        owner.motion, "state", "stopping"
    )
    owner.key(choice, 2_000_000_000)
    owner.readers.read.side_effect = ValueError("readback lost while stopping")
    owner.step(2_100_000_000)
    assert owner.phase == "cancelling"
    assert owner.rejection.choice == ("abort" if choice == "a" else None)
    owner.recorder.poll.return_value = [("cancelled", {})]
    owner.motion.state = "held"
    owner.step(2_200_000_000)
    assert owner.phase == "blocked"
    assert owner.done == (choice == "q")
