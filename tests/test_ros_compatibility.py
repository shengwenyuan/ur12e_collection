"""Validate standard ROS 2 CDR payloads when the Jazzy runtime is available."""

import json

from mcap.reader import make_reader
import pytest

from ur12e_collection import codecs, storage


def test_jazzy_deserializes_standard_episode_messages(
    tmp_path, snapshot, group_factory
):
    serialization = pytest.importorskip("rclpy.serialization")
    sensor = pytest.importorskip("sensor_msgs.msg")
    std = pytest.importorskip("std_msgs.msg")
    video = pytest.importorskip("foxglove_msgs.msg")
    writer = storage.EpisodeWriter(
        tmp_path / "ros-cdr", snapshot, simulated=True
    )
    group = group_factory()
    writer.submit(group)
    writer.finish()
    seen = set()
    with (writer.destination / "episode.mcap").open("rb") as stream:
        for schema, channel, message in make_reader(stream).iter_messages():
            if schema.name == "sensor_msgs/msg/CompressedImage":
                image = serialization.deserialize_message(
                    message.data, sensor.CompressedImage
                )
                decoded = codecs.decode_depth(bytes(image.data))
                assert codecs.depth_digest(decoded) == codecs.depth_digest(
                    group.anchor.payload.depth
                )
                assert (
                    image.header.stamp.sec * 1_000_000_000
                    + image.header.stamp.nanosec
                    == message.publish_time
                )
                seen.add(channel.topic)
            elif schema.name == "foxglove_msgs/msg/CompressedVideo":
                image = serialization.deserialize_message(
                    message.data, video.CompressedVideo
                )
                assert image.format == "h264"
                assert {5, 7, 8} <= codecs.nal_types(bytes(image.data))
                seen.add(channel.topic)
            elif schema.name == "std_msgs/msg/String":
                record = serialization.deserialize_message(
                    message.data, std.String
                )
                assert json.loads(record.data)["schema_version"] == 1
                seen.add(channel.topic)
    assert len(seen) == 8


def test_jazzy_rosbag_reader_handles_ordered_mcap(
    tmp_path, snapshot, group_factory
):
    rosbag = pytest.importorskip("rosbag2_py")
    writer = storage.EpisodeWriter(
        tmp_path / "rosbag", snapshot, simulated=True
    )
    writer.submit(group_factory())
    writer.finish()
    reader = rosbag.SequentialReader()
    reader.open(
        rosbag.StorageOptions(
            uri=str(writer.destination / "episode.mcap"), storage_id="mcap"
        ),
        rosbag.ConverterOptions("cdr", "cdr"),
    )
    rows = []
    while reader.has_next():
        rows.append(reader.read_next())
    assert len(rows) == 8
    assert rows[0][0] == "metadata/episode"
    assert all(a[2] < b[2] for a, b in zip(rows, rows[1:]))
