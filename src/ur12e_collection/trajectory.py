"""Verified local trajectory export with distinct commanded/measured streams."""

import collections
import json

from ur12e_collection import contracts, filesystem, projection, storage


def export(source, destination):
    """Publish a removable JSONL bundle without retiming or robot access."""
    identities = {
        name: projection.digest(source / name)
        for name in ("episode.mcap", "metadata.json", "outcome.json")
    }
    checksum = identities["episode.mcap"]
    storage.verify_episode(source)
    metadata = json.loads((source / "metadata.json").read_text())
    if "control" not in metadata["snapshot"]:
        raise ValueError("trajectory export requires a controlled episode")
    if destination.exists() or destination.name.endswith(".partial"):
        raise ValueError("trajectory destination must be new and complete")
    partial = destination.with_name(destination.name + ".partial")
    partial.mkdir(parents=True)
    counts = collections.Counter()
    with (partial / "trajectory.jsonl").open("x", encoding="utf-8") as output:
        for topic, decoded in projection.messages(
            source / "episode.mcap",
            (
                "control/authority",
                "leader/state",
                "control/command",
                "follower/state",
            ),
        ):
            value = json.loads(decoded.data)
            output.write(
                json.dumps({"topic": topic, "record": value}, allow_nan=False)
                + "\n"
            )
            counts[value["kind"]] += 1
    if any(
        projection.digest(source / name) != digest
        for name, digest in identities.items()
    ):
        raise ValueError("trajectory source changed during export")
    report = {
        "schema_version": 1,
        "source_mcap_sha256": checksum,
        "source_sha256": identities,
        "outcome": json.loads((source / "outcome.json").read_text()),
        "joint_names": contracts.JOINT_NAMES,
        "joint_unit": "rad",
        "counts": dict(counts),
        "snapshot": metadata["snapshot"],
        "association": "independent source records; no interpolation",
    }
    (partial / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    filesystem.publish(partial, destination)
    return report
