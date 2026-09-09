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
            elif schema.name == "std_msgs/msg/String":
                record = serialization.deserialize_message(
                    message.data, std.String
                )
                assert json.loads(record.data)["schema_version"] == 1
                seen.add(channel.topic)
    assert len(seen) == 5
