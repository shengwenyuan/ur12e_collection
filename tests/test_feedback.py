"""Read-only protocol, failure, provenance and complete-file integration tests."""

import dataclasses
import json
import queue
import threading
from unittest import mock

import pytest
from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory

from ur12e_collection import (
    archive,
    contracts,
    feedback,
    feedback_source,
    hande,
    session,
    shadow,
    snapshots,
    storage,
    synthetic,
    ur,
    wire,
)


def _socket(payload):
    connection = mock.Mock()
    connection.recv.side_effect = [bytes([v]) for v in payload] + [b""]
    return connection


def test_hande_get_only_and_raw_values():
    values = (3, 255, 0, 2, 9, 17)
    payload = b"".join(
        f"{k} {v:03d}\n".encode() for k, v in zip(hande.REGISTERS, values)
    )
    connection = _socket(payload)
    with mock.patch.object(
        hande.socket, "create_connection", return_value=connection
    ):
        reader = hande.Reader("fixture", 63352)
        registers, _ = reader.read()
        reader.close()
    assert dict(registers) == dict(zip(hande.REGISTERS, values))
    assert [c.args[0] for c in connection.sendall.call_args_list] == [
        f"GET {key}\n".encode() for key in hande.REGISTERS
    ]
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "reply",
    [
        b"POS -1\n",
        b"POS 256\n",
        b"PRE 1\n",
        b"POS x\n",
        b"POS 1 extra\n",
        b"POS 1",
        b"x" * 64,
        b"\xff\n",
    ],
)
def test_hande_bad_reply_closes_without_retry(reply):
    connection = _socket(reply)
    with mock.patch.object(
        hande.socket, "create_connection", return_value=connection
    ):
        reader = hande.Reader("fixture", 63352)
        with pytest.raises((ValueError, OSError)):
            reader.read()
        with pytest.raises(RuntimeError, match="closed"):
            reader.read()
    connection.sendall.assert_called_once_with(b"GET POS\n")
    connection.close.assert_called_once()


def test_drip_feed_cannot_extend_absolute_deadline():
    connection = _socket(b"POS 3\n")
    with mock.patch.object(
        wire.time, "monotonic_ns", side_effect=[0, 80, 160, 240, 320]
    ):
        with pytest.raises(TimeoutError, match="deadline"):
            wire.line(connection, 250, 64)
    assert connection.recv.call_count == 4


def test_ur_stream_uses_only_output_interface_and_disconnects():
    allowed = [
        "getTimestamp",
        "getActualQ",
        "getActualQd",
        "getActualCurrent",
        "getActualTCPPose",
        "getRobotMode",
        "getSafetyMode",
        "isConnected",
        "disconnect",
    ]
    receiver = mock.Mock(spec_set=allowed)
    receiver.getTimestamp.return_value = 2.0
    for name in allowed[1:5]:
        getattr(receiver, name).return_value = [0.0] * 6
    receiver.getRobotMode.return_value = 3
    receiver.getSafetyMode.return_value = 7
    receiver.isConnected.return_value = True
    module = mock.Mock()
    module.RTDEReceiveInterface.return_value = receiver
    identity = {
        "state": "available",
        "responses": {"get serial number": "fixture"},
    }
    with (
        mock.patch.dict("sys.modules", {"rtde_receive": module}),
        mock.patch.object(ur, "dashboard", return_value=identity),
    ):
        source = feedback_source.ur_stream(
            {"host": "host", "serial": "fixture"}, threading.Event()
        )
        assert next(source)["source_id"] == "fixture"
        sample = next(source)
        source.close()
    module.RTDEReceiveInterface.assert_called_once_with(
        "host", 125.0, feedback_source.UR_OUTPUTS
    )
    assert (
        sample.robot_mode == 3
        and sample.provenance.time.source_ns == 2_000_000_000
    )
    receiver.disconnect.assert_called_once()
    assert all(
        not name.startswith("input") for name in feedback_source.UR_OUTPUTS
    )


def test_ur_bracket_refuses_incoherent_getters():
    receiver = mock.Mock()
    receiver.getTimestamp.side_effect = range(10)
    with pytest.raises(RuntimeError, match="timestamp bracket"):
        ur.coherent_sample(receiver)


def _samples():
    values = []
    for device in feedback.DEVICES:
        source = feedback_source.synthetic_stream(device, threading.Event())
        next(source)
        values.append(next(source))
        source.close()
    return values


def _snapshot(snapshot):
    snapshot["feedback"] = {
        "read_only": True,
        "publish_time_basis": "host_receipt_mapped_unix",
        "monotonic_to_unix_ns": 1_700_000_000_000_000_000,
        "stale_ns": 500_000_000,
        "ur_read_hz": 30,
        "hande_poll_interval_ns": 100_000_000,
        "association": "independent_receipts_no_interpolation",
        "devices": {
            d: {"source_id": "synthetic-" + d, "transport": "synthetic"}
            for d in feedback.DEVICES
        },
    }
    return snapshots.copy(snapshot)


@pytest.mark.parametrize("change", ["sequence", "receipt", "controller"])
def test_feedback_discontinuities_fail(change):
    sample = _samples()[0]
    device = feedback._Device(None, None, None, {"source_id": "synthetic-ur"})
    device.observe(sample)
    p = sample.provenance
    time = dataclasses.replace(
        p.time,
        received_monotonic_ns=p.time.received_monotonic_ns + 1,
        source_ns=p.time.source_ns + 1,
    )
    p = dataclasses.replace(p, sequence=1, time=time)
    if change == "sequence":
        p = dataclasses.replace(p, sequence=3)
    elif change == "receipt":
        p = dataclasses.replace(
            p,
            time=dataclasses.replace(
                time,
                received_monotonic_ns=sample.provenance.time.received_monotonic_ns,
            ),
        )
    else:
        p = dataclasses.replace(p, time=dataclasses.replace(time, source_ns=0))
    with pytest.raises(ValueError):
        device.observe(dataclasses.replace(sample, provenance=p))


@pytest.mark.parametrize("fault", ["exit", "stale", "reported"])
def test_supervisor_surfaces_source_fault(fault):
    owner = feedback.Feedback(synthetic.configuration(), "synthetic")
    device = feedback._Device(
        mock.Mock(),
        queue.Queue(),
        mock.Mock(),
        {"source_id": "synthetic-ur"},
        last_receipt=0,
    )
    device.status.poll.return_value = fault == "reported"
    device.status.recv.return_value = ("error", "queue overflow")
    device.process.is_alive.return_value = fault != "exit"
    owner._devices["ur"] = device
    with pytest.raises((RuntimeError, TimeoutError)):
        owner.read()


def test_forced_feedback_cleanup_is_visible():
    owner = feedback.Feedback(synthetic.configuration(), "synthetic")
    device = feedback._Device(mock.Mock(exitcode=-15), mock.Mock(), mock.Mock())
    device.status.poll.return_value = False
    owner._devices["ur"] = device
    with (
        mock.patch.object(feedback.workers, "stop"),
        pytest.raises(RuntimeError, match="forced cleanup"),
    ):
        owner.close()
    device.status.close.assert_called_once()


@pytest.mark.parametrize(
    "fault", ["missing", "action", "timestamp", "identity"]
)
def test_feedback_archive_rejects_invalid_records(
    tmp_path, snapshot, group_factory, fault
):
    snapshot = _snapshot(snapshot)
    writer = storage.EpisodeWriter(tmp_path / fault, snapshot, simulated=True)
    writer.submit(group_factory())
    offset = snapshot["feedback"]["monotonic_to_unix_ns"]
    samples = _samples()
    if fault == "missing":
        samples = samples[:1]
    if fault == "action":
        samples[0] = contracts.LeaderIntent(
            samples[0].provenance, (0.0,) * 6, 0
        )
    if fault == "identity":
        samples[0] = dataclasses.replace(
            samples[0],
            provenance=dataclasses.replace(
                samples[0].provenance, source_id="wrong"
            ),
        )
    writer.submit_records(
        tuple(
            (
                s,
                s.provenance.time.received_monotonic_ns
                + offset
                + (1 if fault == "timestamp" else 0),
            )
            for s in samples
        )
    )
    with pytest.raises(storage.RecordingError):
        writer.finish()
    assert writer.wait_closed() and not writer.destination.exists()


def test_readonly_two_episode_files_have_no_actions(tmp_path):
    options = shadow.Options(
        "synthetic",
        tmp_path / "batch",
        "test",
        episodes=2,
        seconds=0.4,
        read_feedback=True,
    )
    report = shadow.run(options)
    assert report["mode"] == "read_only_observation"
    for episode in report["episodes"]:
        path = options.output / episode["episode"]
        result = storage.verify_episode(path)
        assert result["counts"]["follower/state"] > 0
        assert "leader/state" not in result["counts"]
        assert "control/command" not in result["counts"]
        records = []
        with (path / "episode.mcap").open("rb") as stream:
            for _, channel, message, decoded in make_reader(
                stream, decoder_factories=[DecoderFactory()]
            ).iter_decoded_messages(topics=["follower/state"]):
                record = json.loads(decoded.data)
                records.append(record)
                receipt = record["provenance"]["time"]["received_monotonic_ns"]
                assert (
                    episode["start_receipt_ns"]
                    <= receipt
                    < episode["stop_receipt_ns"]
                )
                assert channel.topic == "follower/state"
                assert (
                    message.publish_time
                    == receipt
                    + episode["recording"]["snapshot"]["feedback"][
                        "monotonic_to_unix_ns"
                    ]
                )
        assert {r["kind"] for r in records} == {"ur_feedback", "hande_feedback"}
        hand = next(r for r in records if r["kind"] == "hande_feedback")
        assert dict(hand["registers"])["POS"] == 3
        assert hand["provenance"]["time"]["source_ns"] is None


def test_final_reader_catches_feedback_identity_corruption(
    tmp_path, snapshot, group_factory
):
    snapshot = _snapshot(snapshot)
    original = archive.ArchiveWriter._write

    def corrupt(owner, topic, kind, value, timestamp, sequence):
        if topic == "follower/state":
            record = json.loads(value["data"])
            record["provenance"]["source_id"] = "tampered"
            value = {"data": json.dumps(record)}
        return original(owner, topic, kind, value, timestamp, sequence)

    with mock.patch.object(archive.ArchiveWriter, "_write", corrupt):
        writer = storage.EpisodeWriter(
            tmp_path / "tamper", snapshot, simulated=True
        )
        writer.submit(group_factory())
        offset = snapshot["feedback"]["monotonic_to_unix_ns"]
        writer.submit_records(
            tuple(
                (s, offset + s.provenance.time.received_monotonic_ns)
                for s in _samples()
            )
        )
        with pytest.raises(storage.RecordingError, match="source differs"):
            writer.finish()
        assert writer.wait_closed()
    assert not writer.destination.exists()


def test_feedback_late_tail_fails_session(snapshot):
    snapshot = _snapshot(snapshot)
    owner = session.Session(snapshot, shadow.matching.MatchConfig())
    sample = _samples()[0]
    receipt = sample.provenance.time.received_monotonic_ns
    owner.writer = mock.Mock()
    owner.state = "recording"
    owner.boundaries = {"start_receipt_ns": receipt + 1}
    owner.submit_feedback([sample])
    owner.writer.submit_records.assert_not_called()
    owner.state = "finalizing"
    owner.boundaries = {
        "start_receipt_ns": receipt - 1,
        "stop_receipt_ns": receipt + 1,
    }
    with pytest.raises(storage.RecordingError, match="capture drain"):
        owner.submit_feedback([sample])
    assert owner.state == "failed"
    owner.writer.abort.assert_called()


def test_worker_overflow_reports_error_without_reconnecting():
    samples = mock.Mock()
    samples.put_nowait.side_effect = queue.Full
    status = mock.Mock()
    feedback._worker(
        "ur", {}, "synthetic", (samples, status, threading.Event())
    )
    messages = [c.args[0] for c in status.send.call_args_list]
    assert messages[0][0] == "ready"
    assert messages[1][0] == "error" and "Full" in messages[1][1]
    samples.put_nowait.assert_called_once()
    status.close.assert_called_once()


def test_feedback_budget_does_not_consume_image_slots(tmp_path, snapshot):
    entered, release = threading.Event(), threading.Event()

    def blocked(owner, writer):
        entered.set()
        assert release.wait(2)
        raise storage.RecordingError("test stopped")

    with mock.patch.object(storage.EpisodeWriter, "_consume", blocked):
        writer = storage.EpisodeWriter(
            tmp_path / "budgets", snapshot, simulated=True, capacity=1
        )
        try:
            assert entered.wait(2)
            writer.submit_records(tuple((s, 1) for s in _samples()) * 32)
            assert writer.health()["queued_feedback"] == 64
            writer.submit_record(
                contracts.LeaderIntent(_samples()[0].provenance, (0.0,) * 6, 0),
                1,
            )
            assert writer.health()["queued"] == 1
            with pytest.raises(storage.RecordingError, match="overflow"):
                writer.submit_records(((_samples()[0], 1),))
        finally:
            release.set()
            writer.abort()
            assert writer.wait_closed()
    assert "queue overflow" in writer.health()["error"]
