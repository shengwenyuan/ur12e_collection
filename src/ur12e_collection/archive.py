"""ROS 2 CDR MCAP records and streaming independent episode verification."""

import collections
import dataclasses
import json
import math
import pathlib
import time

import av
from mcap.reader import make_reader
from mcap.writer import CompressionType
from mcap_ros2.decoder import DecoderFactory
from mcap_ros2.writer import Writer

from ur12e_collection import codecs
from ur12e_collection import contracts
from ur12e_collection import matching

_TIME = (
    "\n"
    + "=" * 80
    + "\nMSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec\n"
)
_SCHEMAS = {
    "json": ("std_msgs/msg/String", "string data\n"),
    "rgb": (
        "foxglove_msgs/msg/CompressedVideo",
        "builtin_interfaces/Time timestamp\nstring frame_id\n"
        "uint8[] data\nstring format\n" + _TIME,
    ),
    "depth": (
        "sensor_msgs/msg/CompressedImage",
        "std_msgs/Header header\nstring format\nuint8[] data\n"
        + "=" * 80
        + "\nMSG: std_msgs/Header\nbuiltin_interfaces/Time stamp\n"
        "string frame_id\n" + _TIME,
    ),
}
RECORD_TYPES = {
    "leader_intent": contracts.LeaderIntent,
    "sent_command": contracts.SentCommand,
    "follower_state": contracts.FollowerState,
}
RECORD_TOPICS = {
    "leader_intent": "leader/state",
    "sent_command": "control/command",
    "follower_state": "follower/state",
}
TIME_SEMANTICS = "ordered_log_acquisition_publish_v1"


def json_text(value: dict) -> str:
    """Produce finite, deterministic JSON; never serialize image arrays."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def snapshot_copy(snapshot: dict) -> dict:
    """Copy explicit station, time and calibration context."""
    result = json.loads(json_text(snapshot))
    for key in ("task", "software_revision", "clock_id"):
        if not isinstance(result.get(key), str) or not result[key]:
            raise ValueError(f"snapshot requires {key}")
    if result.get("clock_epoch") != "unix" or "calibration" not in result:
        raise ValueError(
            "declare a Unix common clock and calibration (or null)"
        )
    cameras = result.get("cameras", {})
    if set(cameras) != set(contracts.CAMERA_ROLES):
        raise ValueError("snapshot requires exactly three camera roles")
    identities = set()
    for camera in cameras.values():
        scale = camera.get("depth_scale_m")
        if (
            type(scale) not in (int, float)
            or not math.isfinite(scale)
            or scale <= 0
        ):
            raise ValueError("positive per-camera depth scale required")
        identity = camera.get("source_id")
        if (
            not isinstance(identity, str)
            or not identity
            or identity in identities
        ):
            raise ValueError("camera source identities must be unique")
        identities.add(identity)
        intrinsics = camera.get("color_intrinsics")
        if not isinstance(intrinsics, dict):
            raise ValueError("camera color intrinsics must be explicit")
        if (intrinsics.get("width"), intrinsics.get("height")) != (640, 480):
            raise ValueError("intrinsics must describe 640x480 color images")
        for key in ("fx", "fy", "ppx", "ppy"):
            if type(intrinsics.get(key)) not in (int, float):
                raise ValueError("finite camera intrinsics required")
        if intrinsics["fx"] <= 0 or intrinsics["fy"] <= 0:
            raise ValueError("camera focal lengths must be positive")
    return result


def frame_from_dict(value: dict) -> matching.Frame:
    """Reconstruct and validate provenance read from an archive."""
    value = dict(value)
    for name in ("color", "depth"):
        item = dict(value[name])
        item["time"] = contracts.SampleTime(**item["time"])
        value[name] = contracts.Provenance(**item)
    return matching.Frame(**value)


class GroupValidator:
    """Validate group provenance, timing and non-reuse at file entry."""

    def __init__(
        self,
        snapshot: dict,
        simulated: bool,
        config: matching.MatchConfig = matching.MatchConfig(),
    ):
        if not isinstance(simulated, bool):
            raise ValueError("synthetic provenance must be an explicit boolean")
        self.snapshot = snapshot
        self.simulated = simulated
        self.config = config
        self.previous: dict[str, matching.Frame] = {}

    def check(self, group: matching.Match) -> None:
        """A forged accepted result cannot bypass recording invariants."""
        if (
            not group.accepted
            or tuple(f.role for f in group.members) != contracts.CAMERA_ROLES
        ):
            raise ValueError(
                "recording requires one accepted ordered camera triple"
            )
        if group.anchor.metadata() != group.members[0].metadata():
            raise ValueError("group anchor differs from wrist member")
        for frame in group.members:
            if (
                frame.clock_id != self.snapshot["clock_id"]
                or frame.color.simulated != self.simulated
            ):
                raise ValueError("group clock or synthetic provenance mismatch")
            if (
                frame.color.source_id
                != self.snapshot["cameras"][frame.role]["source_id"]
            ):
                raise ValueError("camera identity differs from snapshot")
            if (
                abs(frame.timestamp_ns - group.anchor.timestamp_ns)
                > self.config.max_skew_ns
            ):
                raise ValueError("group exceeds configured skew limit")
            previous = self.previous.get(frame.role)
            if previous is not None:
                if (
                    frame.generation != previous.generation
                    or matching.freshness(frame, previous) != "accepted"
                ):
                    raise ValueError(
                        "group repeats a frame or crosses a source restart"
                    )
        self.previous = {
            f.role: dataclasses.replace(f, payload=None) for f in group.members
        }

    def context(self) -> dict:
        """Describe the recording contract independently of station facts."""
        return {
            "schema_version": 1,
            "snapshot": self.snapshot,
            "simulated": self.simulated,
            "matching": dataclasses.asdict(self.config),
            "time_semantics": TIME_SEMANTICS,
        }


def _stamp(timestamp_ns: int) -> dict:
    if (
        not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool)
    ) or not 0 <= timestamp_ns < (2**31) * 1_000_000_000:
        raise ValueError(
            "timestamp must fit ROS 2 Time on the declared Unix clock"
        )
    seconds, nanos = divmod(timestamp_ns, 1_000_000_000)
    return {"sec": seconds, "nanosec": nanos}


class ArchiveWriter:
    """Single-thread owner of codecs and a caller-owned binary output stream."""

    def __init__(
        self,
        stream,
        snapshot: dict,
        simulated: bool,
        crf: int,
        *,
        config: matching.MatchConfig = matching.MatchConfig(),
    ):
        self.writer = Writer(stream, compression=CompressionType.NONE)
        self.schemas = {
            k: self.writer.register_msgdef(*v) for k, v in _SCHEMAS.items()
        }
        self.video = {
            r: codecs.VideoEncoder(crf) for r in contracts.CAMERA_ROLES
        }
        self.validator = GroupValidator(snapshot, simulated, config)
        self.counts = collections.Counter()
        self.payload_bytes = collections.Counter()
        self.encode_ns = collections.Counter()
        self.max_encode_ns = collections.Counter()
        self._log_time = -1

    def _write(
        self,
        topic: str,
        kind: str,
        value: dict,
        timestamp_ns: int,
        sequence: int,
    ) -> None:
        _stamp(timestamp_ns)
        if topic != "metadata/episode" and not self.counts["metadata/episode"]:
            self._write(
                "metadata/episode",
                "json",
                {"data": json_text(self.validator.context())},
                timestamp_ns,
                0,
            )
        # Preserve acquisition time separately from deterministic replay order.
        self._log_time = max(timestamp_ns, self._log_time + 1)
        self.writer.write_message(
            topic,
            self.schemas[kind],
            value,
            log_time=self._log_time,
            publish_time=timestamp_ns,
            sequence=sequence,
        )
        self.counts[topic] += 1
        self.payload_bytes[topic] += len(
            value["data"].encode() if kind == "json" else value["data"]
        )

    def group(self, group: matching.Match) -> None:
        """Encode an accepted triple without persisting raw duplicates."""
        self.validator.check(group)
        for frame in group.members:
            _stamp(frame.timestamp_ns)
            _stamp(frame.depth_timestamp_ns)
            if not isinstance(frame.payload, codecs.Images):
                raise ValueError("accepted group requires owned RGB-D arrays")
            frame.payload.validate()
        images = []
        info = group.metadata()
        info["depth_sha256"] = {}
        for frame in group.members:
            started = time.perf_counter_ns()
            rgb = self.video[frame.role].encode(
                frame.payload.rgb, frame.timestamp_ns
            )
            self._timing(frame.role + "/rgb", started)
            started = time.perf_counter_ns()
            depth = codecs.encode_depth(frame.payload.depth)
            self._timing(frame.role + "/depth", started)
            info["depth_sha256"][frame.role] = codecs.depth_digest(
                frame.payload.depth
            )
            images.append((frame, rgb, depth))
        index = self.counts["camera/frame_set"]
        self._write(
            "camera/frame_set",
            "json",
            {"data": json_text(info)},
            group.anchor.timestamp_ns,
            index,
        )
        for frame, rgb, depth in images:
            stamp = _stamp(frame.timestamp_ns)
            optical = frame.role + "_color_optical_frame"
            self._write(
                f"camera/{frame.role}/rgb",
                "rgb",
                {
                    "timestamp": stamp,
                    "frame_id": optical,
                    "format": "h264",
                    "data": rgb,
                },
                frame.timestamp_ns,
                index,
            )
            self._write(
                f"camera/{frame.role}/depth",
                "depth",
                {
                    "header": {
                        "stamp": _stamp(frame.depth_timestamp_ns),
                        "frame_id": optical,
                    },
                    "format": "16UC1; png",
                    "data": depth,
                },
                frame.depth_timestamp_ns,
                index,
            )

    def rejection(self, group: matching.Match) -> None:
        """Retain rejected-anchor diagnostics without storing camera images."""
        if group.accepted:
            raise ValueError("accepted groups are not rejection diagnostics")
        self._write(
            "diagnostics/frame_rejection",
            "json",
            {"data": json_text(group.metadata())},
            group.anchor.timestamp_ns,
            self.counts["diagnostics/frame_rejection"],
        )

    def _timing(self, name: str, started: int) -> None:
        elapsed = time.perf_counter_ns() - started
        self.encode_ns[name] += elapsed
        self.max_encode_ns[name] = max(self.max_encode_ns[name], elapsed)

    def record(self, record, timestamp_ns: int) -> None:
        """Keep intent, commands and actual state in distinct typed topics."""
        if type(record) not in RECORD_TYPES.values():
            raise ValueError("unsupported M10 record")
        if record.provenance.simulated != self.validator.simulated:
            raise ValueError("mixed synthetic and physical record provenance")
        topic = RECORD_TOPICS[record.kind]
        self._write(
            topic,
            "json",
            {"data": json_text(dataclasses.asdict(record))},
            timestamp_ns,
            self.counts[topic],
        )

    def finish(self) -> None:
        """Flush every encoder and write the MCAP summary/footer."""
        for video in self.video.values():
            video.finish()
        self.writer.finish()


def _record_check(info: dict, simulated: bool) -> None:
    kind = info.pop("kind")
    if info.pop("schema_version") != 1:
        raise ValueError("unsupported control schema version")
    provenance = info["provenance"]
    provenance["time"] = contracts.SampleTime(**provenance["time"])
    info["provenance"] = contracts.Provenance(**provenance)
    if info.get("joint_positions_rad") is not None:
        info["joint_positions_rad"] = tuple(info["joint_positions_rad"])
    record = RECORD_TYPES[kind](**info)
    if record.provenance.simulated != simulated:
        raise ValueError("mixed provenance in control record")


class _Verifier:
    """Consume file-order records with bounded per-group verification state."""

    def __init__(
        self, snapshot: dict, simulated: bool, config: matching.MatchConfig
    ):
        self.validator = GroupValidator(
            snapshot_copy(snapshot), simulated, config
        )
        self.decoders = {
            r: av.CodecContext.create("h264", "r")
            for r in contracts.CAMERA_ROLES
        }
        self.counts = collections.Counter()
        self.expected = collections.deque()
        self._log_time = -1

    def group(self, info: dict, message) -> None:
        """Validate group provenance before its six payloads."""
        if self.expected or info["schema_version"] != 1:
            raise ValueError("incomplete group or unsupported group schema")
        members = tuple(frame_from_dict(f) for f in info["members"])
        group = matching.Match(
            frame_from_dict(info["anchor"]),
            members,
            info["reason"],
            info["decided_monotonic_ns"],
        )
        self.validator.check(group)
        if info["skews_ns"] != group.metadata()["skews_ns"]:
            raise ValueError("group skews differ from source timestamps")
        if message.sequence != self.counts["camera/frame_set"]:
            raise ValueError("group sequence is discontinuous")
        if message.publish_time != group.anchor.timestamp_ns:
            raise ValueError("group acquisition timestamp changed")
        for frame in members:
            for kind in ("rgb", "depth"):
                self.expected.append(
                    (frame, kind, info["depth_sha256"][frame.role])
                )

    def image(self, schema, topic: str, message, decoded) -> None:
        """Check image association, source time, spatial frame and decoding."""
        if not self.expected:
            raise ValueError("image has no group association")
        frame, kind, digest = self.expected.popleft()
        if (
            topic != f"camera/{frame.role}/{kind}"
            or schema.name != _SCHEMAS[kind][0]
        ):
            raise ValueError("image topic/schema differs from group")
        timestamp = (
            frame.timestamp_ns if kind == "rgb" else frame.depth_timestamp_ns
        )
        if message.publish_time != timestamp:
            raise ValueError("image acquisition timestamp changed")
        if message.sequence != self.counts["camera/frame_set"] - 1:
            raise ValueError("image group index differs")
        stamp = decoded.timestamp if kind == "rgb" else decoded.header.stamp
        optical = decoded.frame_id if kind == "rgb" else decoded.header.frame_id
        if stamp.sec * 1_000_000_000 + stamp.nanosec != timestamp:
            raise ValueError("ROS image timestamp differs from acquisition")
        if optical != frame.role + "_color_optical_frame":
            raise ValueError("image optical frame changed")
        data = bytes(decoded.data)
        if kind == "depth":
            if (
                decoded.format != "16UC1; png"
                or codecs.depth_digest(codecs.decode_depth(data)) != digest
            ):
                raise ValueError("depth format or pixel digest differs")
        else:
            self.rgb(frame.role, topic, decoded.format, data)

    def rgb(self, role: str, topic: str, encoding: str, data: bytes) -> None:
        """Decode exactly one non-B frame with an independent first keyframe."""
        types = codecs.nal_types(data)
        if encoding != "h264" or not types:
            raise ValueError("RGB is not Annex B H.264")
        if (self.counts[topic] == 0 or 5 in types) and not {5, 7, 8} <= types:
            raise ValueError("keyframe lacks independent IDR/SPS/PPS")
        frames = self.decoders[role].decode(av.Packet(data))
        if (
            len(frames) != 1
            or (frames[0].width, frames[0].height) != (640, 480)
            or frames[0].pict_type == 3
        ):
            raise ValueError("RGB packet does not decode one non-B frame")

    def consume(self, schema, channel, message, decoded) -> None:
        """Dispatch CDR records without retaining episode images."""
        topic = channel.topic
        if schema.encoding != "ros2msg" or channel.message_encoding != "cdr":
            raise ValueError("unsupported MCAP message encoding")
        _stamp(message.publish_time)
        if message.log_time != max(message.publish_time, self._log_time + 1):
            raise ValueError("record violates ordered log timeline")
        self._log_time = message.log_time
        if topic.startswith("camera/") and topic != "camera/frame_set":
            self.image(schema, topic, message, decoded)
        else:
            if schema.name != _SCHEMAS["json"][0]:
                raise ValueError("metadata/control JSON schema changed")
            self.json_record(topic, message, json.loads(decoded.data))
        self.counts[topic] += 1

    def json_record(self, topic: str, message, info: dict) -> None:
        """Keep snapshot, group, rejection and control meanings separate."""
        if topic == "metadata/episode":
            expected = self.validator.context()
            if self.counts or info != expected:
                raise ValueError(
                    "episode snapshot is missing, repeated or changed"
                )
        elif not self.counts["metadata/episode"]:
            raise ValueError("episode snapshot must precede observations")
        elif topic == "camera/frame_set":
            self.group(info, message)
        elif topic in RECORD_TOPICS.values():
            if topic != RECORD_TOPICS[info["kind"]]:
                raise ValueError("control topic semantics changed")
            _record_check(info, self.validator.simulated)
        elif topic == "diagnostics/frame_rejection":
            frame = frame_from_dict(info["anchor"])
            if (
                info["reason"] == "accepted"
                or info["members"]
                or info["schema_version"] != 1
                or message.publish_time != frame.timestamp_ns
            ):
                raise ValueError("accepted group mislabeled as rejection")
            if frame.color.simulated != self.validator.simulated:
                raise ValueError("rejection provenance differs")
        else:
            raise ValueError(f"unexpected episode topic: {topic}")

    def finish(self) -> None:
        """Reject missing payloads, empty recordings and delayed frames."""
        if self.expected or not self.counts["camera/frame_set"]:
            raise ValueError("empty or incomplete episode")
        if any(decoder.decode(None) for decoder in self.decoders.values()):
            raise ValueError("unexpected delayed decoded frames")


def verify_mcap(
    path: pathlib.Path,
    snapshot: dict,
    simulated: bool,
    config: matching.MatchConfig = matching.MatchConfig(),
) -> dict:
    """Stream/decode every stored image and independently check association."""
    verifier = _Verifier(snapshot, simulated, config)
    with path.open("rb") as stream:
        reader = make_reader(
            stream, validate_crcs=True, decoder_factories=[DecoderFactory()]
        )
        if (
            reader.get_header().profile != "ros2"
            or reader.get_summary() is None
        ):
            raise ValueError("missing ROS 2 MCAP profile or summary")
        for record in reader.iter_decoded_messages(log_time_order=False):
            verifier.consume(*record)
    verifier.finish()
    return {
        "counts": dict(verifier.counts),
        "mcap_bytes": path.stat().st_size,
        "all_depth_hashes_verified": True,
        "all_rgb_frames_decoded": True,
    }
