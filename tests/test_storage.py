"""Real offline codec/MCAP round trips and bounded failure semantics."""

import dataclasses
import json
import threading
from unittest import mock

import av
import numpy as np
import pytest

from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory

from ur12e_collection import archive, cli, codecs, contracts, matching, storage


def test_depth_exact_and_rgb_quality(group_factory):
    images = group_factory().anchor.payload
    assert np.array_equal(
        codecs.decode_depth(codecs.encode_depth(images.depth)), images.depth
    )
    packet = codecs.VideoEncoder().encode(images.rgb, 1_000_000)
    decoder = av.CodecContext.create("h264", "r")
    rgb = decoder.decode(av.Packet(packet))[0].to_ndarray(format="rgb24")
    assert codecs.rgb_psnr(images.rgb, rgb) > 30
    assert {5, 7, 8} <= codecs.nal_types(packet)


def test_independent_episodes_roundtrip_with_raw_control(
    tmp_path, snapshot, group_factory
):
    for index in range(2):
        writer = storage.EpisodeWriter(
            tmp_path / f"ep-{index}", snapshot, simulated=True, capacity=8
        )
        first = group_factory(0)
        writer.submit(first)
        writer.submit(
            group_factory(2)
        )  # Preserve the missing time; do not retime to 30 Hz.
        intent = contracts.LeaderIntent(first.anchor.color, (0.0,) * 6, 255)
        writer.submit_record(intent, first.anchor.timestamp_ns)
        report = writer.finish()
        assert not writer.partial.exists()
        assert (
            storage.verify_episode(writer.destination)["counts"][
                "camera/frame_set"
            ]
            == 2
        )
        assert report["payload_bytes"]["camera/wrist/depth"] > 0
        assert (
            report["snapshot"]["cameras"]["wrist"]["depth_scale_m"] == 0.000123
        )


def test_timing_collision_and_bad_depth_fail(tmp_path, snapshot, group_factory):
    encoder = codecs.VideoEncoder()
    rgb = group_factory().anchor.payload.rgb
    encoder.encode(rgb, 10_000)
    with pytest.raises(ValueError):
        encoder.encode(rgb, 10_001)
    writer = storage.EpisodeWriter(
        tmp_path / "invalid", snapshot, simulated=True
    )
    group = group_factory()
    frame = dataclasses.replace(
        group.anchor, payload=codecs.Images(rgb, np.zeros((480, 640), np.uint8))
    )
    writer.submit(
        dataclasses.replace(
            group, anchor=frame, members=(frame,) + group.members[1:]
        )
    )
    with pytest.raises(storage.RecordingError):
        writer.finish()
    assert writer.wait_closed()
    assert not writer.destination.exists() and writer.partial.exists()


def test_queue_overflow_aborts_instead_of_dropping(
    tmp_path, snapshot, group_factory
):
    entered, release = threading.Event(), threading.Event()
    original = archive.ArchiveWriter.group

    def slow(writer, group):
        entered.set()
        assert release.wait(5)
        original(writer, group)

    with mock.patch.object(archive.ArchiveWriter, "group", slow):
        writer = storage.EpisodeWriter(
            tmp_path / "overflow", snapshot, simulated=True, capacity=1
        )
        writer.submit(group_factory(0))
        assert entered.wait(5)
        writer.submit(group_factory(1))
        with pytest.raises(storage.RecordingError, match="overflow"):
            writer.submit(group_factory(2))
        release.set()
        assert writer.wait_closed()
    assert not writer.destination.exists()


def test_timeout_cannot_commit_later(tmp_path, snapshot, group_factory):
    entered, release = threading.Event(), threading.Event()
    original = archive.verify_mcap

    def slow(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    with mock.patch.object(archive, "verify_mcap", slow):
        writer = storage.EpisodeWriter(
            tmp_path / "timeout", snapshot, simulated=True
        )
        writer.submit(group_factory())
        with pytest.raises(storage.RecordingError):
            writer.finish(timeout=0.5)
        assert entered.is_set()
        release.set()
        assert writer.wait_closed()
    assert not writer.destination.exists()


def test_existing_episode_and_concurrent_name_are_preserved(tmp_path, snapshot):
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep"
    sentinel.write_text("unchanged")
    with pytest.raises(FileExistsError):
        storage.EpisodeWriter(destination, snapshot, simulated=True)
    assert sentinel.read_text() == "unchanged"
    writer = storage.EpisodeWriter(
        tmp_path / "reserved", snapshot, simulated=True
    )
    with pytest.raises(FileExistsError):
        storage.EpisodeWriter(writer.destination, snapshot, simulated=True)
    writer.abort()
    assert writer.wait_closed()


@pytest.mark.parametrize("failure", ["encode", "disk", "verify"])
def test_injected_failures_remain_partial(
    tmp_path, snapshot, group_factory, failure
):
    target = {
        "encode": "ur12e_collection.codecs.VideoEncoder.encode",
        "disk": "ur12e_collection.archive.Writer.write_message",
        "verify": "ur12e_collection.archive.verify_mcap",
    }[failure]
    with mock.patch(target, side_effect=OSError("injected failure")):
        writer = storage.EpisodeWriter(
            tmp_path / failure, snapshot, simulated=True
        )
        with pytest.raises(storage.RecordingError):
            writer.submit(group_factory())
            writer.finish()
        assert writer.wait_closed()
    assert not writer.destination.exists()
    assert (writer.partial / "failure.json").exists()


def test_corrupted_mcap_is_not_accepted(tmp_path, snapshot, group_factory):
    writer = storage.EpisodeWriter(
        tmp_path / "corrupt", snapshot, simulated=True
    )
    writer.submit(group_factory())
    writer.finish()
    path = writer.destination / "episode.mcap"
    data = path.read_bytes()
    path.write_bytes(data[:-40])
    with pytest.raises(ValueError):
        storage.verify_episode(writer.destination)


@pytest.mark.parametrize("changed_camera", [0, 1, 2])
def test_final_verification_rejects_valid_png_with_wrong_pixels(
    tmp_path, snapshot, group_factory, changed_camera
):
    encode = codecs.encode_depth
    calls = 0

    def changed_payload(depth):
        nonlocal calls
        pixels = depth.copy()
        if calls == changed_camera:
            pixels[0, 0] ^= 1
        calls += 1
        return encode(pixels)

    # A decodable PNG can still differ from the acquired depth. The final
    # archive check must catch this independently of any inline codec check.
    with mock.patch.object(codecs, "encode_depth", changed_payload):
        writer = storage.EpisodeWriter(
            tmp_path / "wrong-pixels", snapshot, simulated=True
        )
        writer.submit(group_factory())
        with pytest.raises(storage.RecordingError, match="pixel digest"):
            writer.finish()
        assert writer.wait_closed()
    assert not writer.destination.exists()
    assert (writer.partial / "failure.json").exists()


def test_matcher_writer_integration_preserves_depth_time_and_rejections(
    tmp_path, snapshot, group_factory, capsys
):
    matcher = matching.Matcher("fixture-unix")
    writer = storage.EpisodeWriter(
        tmp_path / "integrated", snapshot, simulated=True
    )
    group = group_factory()
    for frame in group.members:
        frame = dataclasses.replace(
            frame, depth_timestamp_ns=frame.timestamp_ns + 1000
        )
        for result in matcher.push(
            frame, frame.color.time.received_monotonic_ns
        ):
            writer.submit(result)
    missing = group_factory(1).anchor
    matcher.push(missing, missing.color.time.received_monotonic_ns)
    for result in matcher.finish(missing.color.time.received_monotonic_ns):
        writer.submit(result)
    writer.submit_record(
        contracts.FollowerState(group.anchor.color, None, 0),
        group.anchor.timestamp_ns,
    )
    writer.submit_record(
        contracts.SentCommand(group.anchor.color, (0.0,) * 6, 255),
        group.anchor.timestamp_ns,
    )
    report = writer.finish()
    assert report["verification"]["counts"]["diagnostics/frame_rejection"] == 1
    with (writer.destination / "episode.mcap").open("rb") as stream:
        records = {
            channel.topic: (message, decoded)
            for _, channel, message, decoded in make_reader(
                stream, decoder_factories=[DecoderFactory()]
            ).iter_decoded_messages()
        }
    depth, _ = records["camera/wrist/depth"]
    rgb, _ = records["camera/wrist/rgb"]
    assert depth.publish_time == rgb.publish_time + 1000
    assert records["metadata/episode"][0].log_time < rgb.log_time
    assert (
        json.loads(records["control/command"][1].data)["gripper_request_raw"]
        == 255
    )
    assert (
        json.loads(records["follower/state"][1].data)["joint_positions_rad"]
        is None
    )
    assert writer.health()["state"] == "committed"
    assert cli.main(["episode", "verify", str(writer.destination)]) == 0
    assert "all_depth_hashes_verified" in capsys.readouterr().out


def test_snapshot_and_duplicate_groups_cannot_be_accepted(
    tmp_path, snapshot, group_factory
):
    bad_snapshot = dict(snapshot, clock_epoch="hardware")
    with pytest.raises(ValueError):
        storage.EpisodeWriter(
            tmp_path / "bad-clock", bad_snapshot, simulated=True
        )
    assert not (tmp_path / "bad-clock.partial").exists()
    writer = storage.EpisodeWriter(
        tmp_path / "duplicate", snapshot, simulated=True
    )
    writer.submit(group_factory())
    writer.submit(group_factory())
    with pytest.raises(storage.RecordingError):
        writer.finish()
    assert writer.wait_closed()
    assert not writer.destination.exists()


def test_empty_episode_and_metadata_mismatch_fail(
    tmp_path, snapshot, group_factory
):
    writer = storage.EpisodeWriter(tmp_path / "empty", snapshot, simulated=True)
    with pytest.raises(storage.RecordingError):
        writer.finish()
    assert writer.wait_closed()
    valid = storage.EpisodeWriter(tmp_path / "valid", snapshot, simulated=True)
    valid.submit(group_factory())
    valid.finish()
    metadata = valid.destination / "metadata.json"
    data = json.loads(metadata.read_text())
    data["snapshot"]["cameras"]["wrist"]["depth_scale_m"] *= 2
    metadata.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="snapshot"):
        storage.verify_episode(valid.destination)


@pytest.mark.parametrize("role", contracts.CAMERA_ROLES)
@pytest.mark.parametrize("depth_delta", [0, -1])
def test_stalled_depth_is_rejected_before_writer_and_recovers(
    tmp_path, snapshot, group_factory, role, depth_delta
):
    matcher = matching.Matcher(snapshot["clock_id"])
    writer = storage.EpisodeWriter(
        tmp_path / "depth-recovery", snapshot, simulated=True, capacity=8
    )
    first = group_factory(0)
    results = []
    for index in range(3):
        group = group_factory(index)
        for frame in group.members:
            if index == 1 and frame.role == role:
                frame = dataclasses.replace(
                    frame,
                    depth_timestamp_ns=first.anchor.depth_timestamp_ns
                    + depth_delta,
                )
            for result in matcher.push(
                frame, frame.color.time.received_monotonic_ns
            ):
                results.append(result)
                writer.submit(result)
    assert [r.reason for r in results] == [
        "accepted",
        "invalid_timing",
        "accepted",
    ]
    report = writer.finish()
    assert report["verification"]["counts"]["camera/frame_set"] == 2
    assert report["verification"]["counts"]["diagnostics/frame_rejection"] == 1
    assert storage.verify_episode(writer.destination) == report["verification"]


def test_sub_microsecond_candidate_never_reaches_encoder(
    tmp_path, snapshot, group_factory
):
    matcher = matching.Matcher(snapshot["clock_id"])
    writer = storage.EpisodeWriter(
        tmp_path / "pts-recovery", snapshot, simulated=True, capacity=8
    )
    results = []
    first = group_factory()
    for index, offset in enumerate((0, 500, 2000)):
        for original in first.members:
            frame = dataclasses.replace(
                original,
                timestamp_ns=original.timestamp_ns + offset,
                depth_timestamp_ns=original.depth_timestamp_ns + offset,
                color=dataclasses.replace(original.color, sequence=index),
                depth=dataclasses.replace(original.depth, sequence=index),
            )
            for result in matcher.push(frame, 1_000_000 + offset):
                results.append(result)
                writer.submit(result)
    assert [r.reason for r in results] == [
        "accepted",
        "invalid_timing",
        "accepted",
    ]
    assert writer.finish()["verification"]["counts"]["camera/frame_set"] == 2


def test_nondefault_matching_contract_survives_recording(
    tmp_path, snapshot, group_factory
):
    config = matching.MatchConfig(max_skew_ns=20_000_000)
    matcher = matching.Matcher(snapshot["clock_id"], config)
    writer = storage.EpisodeWriter(
        tmp_path / "custom-skew", snapshot, simulated=True, match_config=config
    )
    group = group_factory()
    results = []
    for frame in group.members:
        if frame.role != "wrist":
            frame = dataclasses.replace(
                frame, timestamp_ns=frame.timestamp_ns + config.max_skew_ns
            )
        results += matcher.push(frame, 21_000_000)
    assert len(results) == 1 and results[0].accepted
    with pytest.raises(ValueError, match="skew"):
        archive.GroupValidator(snapshot, True).check(results[0])
    writer.submit(results[0])
    report = writer.finish()
    assert report["matching"]["max_skew_ns"] == config.max_skew_ns
    assert storage.verify_episode(writer.destination) == report["verification"]
    metadata = writer.destination / "metadata.json"
    report["matching"]["max_skew_ns"] += 1
    metadata.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot"):
        storage.verify_episode(writer.destination)


@pytest.mark.parametrize("control_first", [False, True])
def test_skew_and_late_records_preserve_both_read_orders(
    tmp_path, snapshot, group_factory, control_first
):
    writer = storage.EpisodeWriter(
        tmp_path / "ordered", snapshot, simulated=True, capacity=8
    )
    group = group_factory()
    members = tuple(
        dataclasses.replace(
            frame,
            timestamp_ns=frame.timestamp_ns + skew,
            depth_timestamp_ns=frame.depth_timestamp_ns + skew + 1000,
        )
        for frame, skew in zip(group.members, (0, -12_000_000, 12_000_000))
    )
    group = dataclasses.replace(group, anchor=members[0], members=members)
    state = contracts.FollowerState(group.anchor.color, None, 255)
    if control_first:
        writer.submit_record(state, group.anchor.timestamp_ns + 100_000_000)
    writer.submit(group)
    writer.submit_record(state, group.anchor.timestamp_ns - 20_000_000)
    writer.submit(dataclasses.replace(group, members=(), reason="missing_view"))
    report = writer.finish()
    path = writer.destination / "episode.mcap"
    orders = []
    for time_order in (False, True):
        with path.open("rb") as stream:
            records = list(
                make_reader(stream).iter_messages(log_time_order=time_order)
            )
        orders.append(
            [
                (c.topic, m.log_time, m.publish_time, m.data)
                for _, c, m in records
            ]
        )
        assert records[0][1].topic == "metadata/episode"
        assert all(
            a[2].log_time < b[2].log_time for a, b in zip(records, records[1:])
        )
        context = next(
            i
            for i, (_, c, _) in enumerate(records)
            if c.topic == "camera/frame_set"
        )
        for frame in members:
            for kind, timestamp in (
                ("rgb", frame.timestamp_ns),
                ("depth", frame.depth_timestamp_ns),
            ):
                index, message = next(
                    (i, m)
                    for i, (_, c, m) in enumerate(records)
                    if c.topic == f"camera/{frame.role}/{kind}"
                )
                assert index > context
                assert message.publish_time == timestamp
    assert orders[0] == orders[1]
    assert storage.verify_episode(writer.destination) == report["verification"]


def test_invalid_last_camera_is_detected_before_any_encoder_advances(
    tmp_path, snapshot, group_factory
):
    group = group_factory()
    last = dataclasses.replace(
        group.members[-1],
        payload=codecs.Images(
            group.anchor.payload.rgb, np.zeros((480, 640), np.uint8)
        ),
    )
    group = dataclasses.replace(group, members=group.members[:-1] + (last,))
    with mock.patch.object(codecs.VideoEncoder, "encode") as encode:
        writer = storage.EpisodeWriter(
            tmp_path / "preflight", snapshot, simulated=True
        )
        writer.submit(group)
        with pytest.raises(storage.RecordingError, match="uint16"):
            writer.finish()
        encode.assert_not_called()
    assert not writer.destination.exists()


@pytest.mark.parametrize("seed", range(5))
def test_jittered_matcher_outputs_obey_recording_contract(
    snapshot, frame_factory, seed
):
    # Exercise composition across deterministic inter-camera arrival orders.
    import random  # Local seed; never alter application randomness.

    randomizer = random.Random(seed)
    matcher = matching.Matcher(snapshot["clock_id"])
    validator = archive.GroupValidator(snapshot, True, matcher.config)
    results = []
    for index in range(60):
        anchor = 100_000_000 + index * 33_333_333
        frames = []
        for role in contracts.CAMERA_ROLES:
            skew = (
                0
                if role == "wrist"
                else randomizer.randint(-16_700_000, 16_700_000)
            )
            frame = frame_factory(
                role, anchor + skew, index, receipt=anchor + 20_000_000
            )
            if index % 5 == 1:
                frame = dataclasses.replace(
                    frame, depth_timestamp_ns=1_700_000_000_000_000_000
                )
            frames.append(frame)
        randomizer.shuffle(frames)
        for frame in frames:
            results += matcher.push(frame, anchor + 20_000_000)
    results += matcher.finish(anchor + 20_000_000)
    assert len(results) == 60
    assert any(r.reason == "invalid_timing" for r in results)
    assert sum(r.accepted for r in results) > 20
    for result in results:
        if result.accepted:
            validator.check(result)
