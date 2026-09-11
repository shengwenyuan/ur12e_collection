"""Disposable lab-image cache; never imports hardware/control adapters."""

import argparse
import contextlib
import hashlib
import json
import pathlib
import time

import av

from ur12e_collection import codecs, contracts, mcap_read


def build(episode: pathlib.Path, output: pathlib.Path) -> dict:
    """Decode complete episodes to disk, preserving exact source provenance."""
    metadata = json.loads((episode / "metadata.json").read_text())
    if metadata.get("state") != "complete" or ".partial" in episode.name:
        raise ValueError("only complete episodes are normal replay inputs")
    if output.exists():
        raise FileExistsError(output)
    partial = output.with_name(output.name + ".partial")
    partial.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    path = episode / "episode.mcap"
    with path.open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    with contextlib.ExitStack() as stack:
        streams = {
            (role, kind): stack.enter_context(
                (partial / f"{role}.{kind}.raw").open("xb")
            )
            for role in contracts.CAMERA_ROLES
            for kind in ("rgb", "depth")
        }
        groups = _decode(path, streams)
    value = {
        "schema_version": 1,
        "origin": "replay",
        "source_mcap_sha256": source_hash,
        "source_episode": str(episode.resolve()),
        "groups": groups,
        "frames_per_role": len(groups),
        "rgb": {
            "dtype": "uint8",
            "shape": [480, 640, 3],
            "lossy_generation": 1,
        },
        "depth": {
            "dtype": "<u2",
            "shape": [480, 640],
            "all_hashes_verified": True,
        },
        "source_metadata": metadata,
        "build_seconds": time.monotonic() - started,
        "raw_bytes": sum(p.stat().st_size for p in partial.glob("*.raw")),
        "limits": [
            "accepted payloads only; missing and rejected images unavailable",
            "RGB has already undergone H264 compression",
            "no USB, RealSense alignment, network or robot-physics replay",
        ],
    }
    (partial / "manifest.json").write_text(json.dumps(value) + "\n")
    partial.rename(output)
    return {
        key: value[key]
        for key in (
            "frames_per_role",
            "raw_bytes",
            "build_seconds",
            "source_mcap_sha256",
        )
    }


def _decode(path, streams):
    """Check ordered image groups while writing bounded decoded payloads."""
    topics = ["camera/frame_set"] + [
        f"camera/{role}/{kind}"
        for role in contracts.CAMERA_ROLES
        for kind in ("rgb", "depth")
    ]
    decoders = {
        role: av.CodecContext.create("h264", "r")
        for role in contracts.CAMERA_ROLES
    }
    groups = []
    pending = set()
    context = None
    for topic, message in mcap_read.messages(path, topics):
        if topic == "camera/frame_set":
            if pending:
                raise ValueError("source group has missing image payloads")
            context = json.loads(message.data)
            if (
                tuple(m["role"] for m in context["members"])
                != contracts.CAMERA_ROLES
            ):
                raise ValueError("invalid source camera roles")
            groups.append(context)
            pending = set(streams)
            continue
        _, role, kind = topic.split("/")
        if context is None or (role, kind) not in pending:
            raise ValueError("image is repeated or lacks group provenance")
        if kind == "rgb":
            frames = decoders[role].decode(av.Packet(bytes(message.data)))
            if len(frames) != 1:
                raise ValueError("source video is not one frame per message")
            pixels = frames[0].to_ndarray(format="rgb24")
            if pixels.shape != (480, 640, 3):
                raise ValueError("source RGB is not 480p")
        else:
            pixels = codecs.decode_depth(bytes(message.data))
            if codecs.depth_digest(pixels) != context["depth_sha256"][role]:
                raise ValueError("source depth pixel hash mismatch")
            pixels = pixels.astype("<u2", copy=False)
        streams[role, kind].write(pixels.tobytes())
        pending.remove((role, kind))
    if pending or not groups:
        raise ValueError("source ends with an incomplete image group")
    return groups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.episode, args.output), indent=2))
