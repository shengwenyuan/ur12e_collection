"""Offline RGB/arm projection with causal association and source clocks."""

import bisect
import hashlib
import json
import pathlib

import av
import numpy as np
from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory

from ur12e_collection import contracts, storage

MAX_AGE_NS = 50_000_000


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


class Timeline:
    """Latest preceding sample, without interpolation or future data."""

    def __init__(self, samples: list):
        self.samples = samples
        self.times = [
            s["provenance"]["time"]["received_monotonic_ns"] for s in samples
        ]
        if not samples or any(
            b <= a for a, b in zip(self.times, self.times[1:])
        ):
            raise ValueError(
                "projection requires a strictly ordered control stream"
            )

    def at(self, receipt_ns: int) -> dict:
        """Reject missing/stale state instead of filling a target or zero."""
        index = bisect.bisect_right(self.times, receipt_ns) - 1
        if index < 0 or receipt_ns - self.times[index] > MAX_AGE_NS:
            raise ValueError("camera has no fresh preceding state/action")
        return self.samples[index]


class Episode:
    """Keep only one episode's scalar timelines; RGB decoding is streaming."""

    def __init__(self, path: pathlib.Path, action_source: str):
        if action_source not in ("sent_command", "leader_intent"):
            raise ValueError("an explicit action source is required")
        self.path = path
        self.action_source = action_source
        self.checksums = {
            name: digest(path / name)
            for name in ("episode.mcap", "metadata.json", "outcome.json")
        }
        storage.verify_episode(path)
        outcome = json.loads(
            (path / "outcome.json").read_text(encoding="utf-8")
        )
        if outcome.get("disposition") != "retained":
            raise ValueError(
                "discarded or interrupted episodes cannot be exported"
            )
        metadata = json.loads(
            (path / "metadata.json").read_text(encoding="utf-8")
        )
        self.snapshot = metadata["snapshot"]
        if (
            "control" not in self.snapshot
            or self.snapshot["control"]["hande"] != "bypassed"
        ):
            raise ValueError(
                "RGB/arm-only projection requires declared controlled arm data"
            )
        self.groups, self.state, self.action = self._scan()
        self.unchanged()

    def _scan(self):
        groups, states, actions = [], [], []
        for topic, decoded in messages(
            self.path / "episode.mcap",
            (
                "camera/frame_set",
                "follower/state",
                "leader/state",
                "control/command",
            ),
        ):
            value = json.loads(decoded.data)
            if topic == "camera/frame_set":
                groups.append(value)
            elif value["kind"] == "follower_state":
                states.append(value)
            elif value["kind"] == self.action_source:
                actions.append(value)
        anchors = [group["anchor"]["color"] for group in groups]
        for previous, anchor in zip(anchors, anchors[1:]):
            if (
                anchor["sequence"] != previous["sequence"] + 1
                or not 16_000_000
                < (anchor["time"]["source_ns"] - previous["time"]["source_ns"])
                < 50_000_000
            ):
                raise ValueError("projection requires contiguous wrist frames")
        return groups, Timeline(states), Timeline(actions)

    def row(self, index: int) -> dict:
        """Preserve source clocks beside the nominal playback timeline."""
        group = self.groups[index]
        receipt = group["anchor"]["color"]["time"]["received_monotonic_ns"]
        state, action = self.state.at(receipt), self.action.at(receipt)
        if (
            state["gripper_position_raw"] is not None
            or action["gripper_request_raw"] is not None
        ):
            raise ValueError(
                "arm-only projection cannot silently drop real gripper values"
            )
        result = {
            "observation.state": np.asarray(
                state["joint_positions_rad"], dtype=np.float32
            ),
            "action": np.asarray(
                action["joint_positions_rad"], dtype=np.float32
            ),
            "source.camera_ns": [
                f["color"]["time"]["source_ns"] for f in group["members"]
            ],
            "source.camera_sequence": [
                f["color"]["sequence"] for f in group["members"]
            ],
            "source.wrist_receipt_ns": [receipt],
            "source.state_receipt_ns": [
                state["provenance"]["time"]["received_monotonic_ns"]
            ],
            "source.action_receipt_ns": [
                action["provenance"]["time"]["received_monotonic_ns"]
            ],
            "source.controller_uptime_ns": [
                state["provenance"]["time"]["source_ns"]
            ],
        }
        return {
            key: (
                np.asarray(value, dtype=np.int64)
                if key.startswith("source.")
                else value
            )
            for key, value in result.items()
        }

    def frames(self):
        """Decode one camera triple at a time; retain original depth in MCAP."""
        decoders = {
            role: av.CodecContext.create("h264", "r")
            for role in contracts.CAMERA_ROLES
        }
        images = {}
        index = 0
        for topic, decoded in messages(
            self.path / "episode.mcap",
            [f"camera/{role}/rgb" for role in contracts.CAMERA_ROLES],
        ):
            role = topic.split("/")[1]
            if role in images:
                raise ValueError("projection RGB group is incomplete")
            frames = decoders[role].decode(av.Packet(bytes(decoded.data)))
            if len(frames) != 1:
                raise ValueError("projection expected one immediate RGB frame")
            images[role] = frames[0].to_ndarray(format="rgb24")
            if len(images) == 3:
                yield self.row(index) | {
                    f"observation.images.{role}": image
                    for role, image in images.items()
                }
                images = {}
                index += 1
        if images or index != len(self.groups):
            raise ValueError(
                "projection RGB count differs from accepted groups"
            )

    def unchanged(self) -> None:
        """Reject a source changed during offline conversion."""
        if any(
            digest(self.path / name) != value
            for name, value in self.checksums.items()
        ):
            raise ValueError("source episode changed during conversion")

    def manifest(self) -> dict:
        """Keep source identity and immutable context beside the projection."""
        return {
            "episode": str(self.path),
            "sha256": self.checksums,
            "snapshot": self.snapshot,
            "frames": len(self.groups),
        }
