"""Measure RGB re-encoding loss against the exact recorded-image fixture."""

import argparse
import json
import pathlib

import av

from .feed import Cache
from ur12e_collection import codecs, contracts, mcap_read


def summarize(values):
    """Keep exact frames separate from finite decibel measurements."""
    finite = [value for value in values if value is not None]
    return {
        "frames": len(values),
        "exact_frames": values.count(None),
        "mean_finite_psnr_db": sum(finite) / len(finite) if finite else None,
        "minimum_psnr_db": min(finite) if finite else None,
    }


def measure(path, cache):
    """Stream one decoded image at a time; this is not a new quality gate."""
    metadata = json.loads((path / "metadata.json").read_text())
    context = metadata["snapshot"]["control"]["inputs"]["cameras"]
    if context["cache_sha256"] != cache.identity:
        raise ValueError("episode and RGB fixture identity differ")
    positions = {
        role: {
            cache.member(role, index)["color"]["sequence"]: index
            for index in range(len(cache.groups))
        }
        for role in contracts.CAMERA_ROLES
    }
    decoders = {
        role: av.CodecContext.create("h264", "r")
        for role in contracts.CAMERA_ROLES
    }
    scores = {role: [] for role in contracts.CAMERA_ROLES}
    group, pending = None, set()
    for topic, message in mcap_read.messages(
        path / "episode.mcap",
        ["camera/frame_set"]
        + [f"camera/{role}/rgb" for role in contracts.CAMERA_ROLES],
    ):
        if topic == "camera/frame_set":
            if pending:
                raise ValueError("group has missing RGB payloads")
            group = json.loads(message.data)
            pending = set(contracts.CAMERA_ROLES)
            continue
        role = topic.split("/")[1]
        if group is None or role not in pending:
            raise ValueError("RGB lacks a unique group association")
        frames = decoders[role].decode(av.Packet(bytes(message.data)))
        if len(frames) != 1:
            raise ValueError("RGB stream is not independently zero-delay")
        member = next(
            value for value in group["members"] if value["role"] == role
        )
        identity = member["color"]["sequence"] % cache.sequence_stride
        reference = cache.arrays[role, "rgb"][positions[role][identity]]
        scores[role].append(
            codecs.rgb_psnr(reference, frames[0].to_ndarray(format="rgb24"))
        )
        pending.remove(role)
    if pending or not all(scores.values()):
        raise ValueError("episode has incomplete RGB coverage")
    return {
        "quality_gate_not_assigned": True,
        "reference": "first-generation H264 decoded cache, not sensor raw RGB",
        "output_rgb_lossy_generation": 2,
        "cache_sha256": cache.identity,
        "roles": {role: summarize(values) for role, values in scores.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=pathlib.Path)
    parser.add_argument("cache", type=pathlib.Path)
    args = parser.parse_args()
    cache = Cache(args.cache)
    try:
        result = measure(args.episode, cache)
    finally:
        cache.close()
    output = args.episode / "rgb-reencode-quality.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
