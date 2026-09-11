"""Neutral streaming readers for verified MCAP audits and replay."""

import hashlib
import pathlib

from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory


def digest(path: pathlib.Path) -> str:
    """Hash a complete source without loading it into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def messages(path, topics):
    """Stream only requested local ROS-CDR topics in recorded file order."""
    with path.open("rb") as stream:
        reader = make_reader(stream, decoder_factories=[DecoderFactory()])
        for _, channel, _, decoded in reader.iter_decoded_messages(
            topics=topics, log_time_order=False
        ):
            yield channel.topic, decoded
