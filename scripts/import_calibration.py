#!/usr/bin/env python3
"""Convert a colleague YAML route offline; no device modules are opened."""

import argparse
import dataclasses
import hashlib
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
# pylint: disable=wrong-import-position
from ur12e_collection import filesystem, station
from ur12e_collection.calibration import (
    aprilgrid,
    deployment,
    importing,
    routes,
)
from ur12e_collection.followers import config as configuration

# pylint: enable=wrong-import-position


def main():
    """Bind measured routes to the setup and preserve their source."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=pathlib.Path)
    parser.add_argument("--role", required=True, choices=tuple(importing.ROLES))
    parser.add_argument("--config", required=True, type=pathlib.Path)
    parser.add_argument("--station", required=True, type=pathlib.Path)
    parser.add_argument("--base-id", required=True)
    parser.add_argument("--mount-id", required=True)
    parser.add_argument("--board-mount-id", required=True)
    parser.add_argument("--board", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    config = configuration.load(args.config)
    camera = station.load(args.station)["cameras"][args.role]
    raw = args.source.read_bytes()
    definition = (
        json.loads(args.board.read_text(encoding="utf-8"))
        if args.board
        else dataclasses.asdict(aprilgrid.Grid())
    )
    context = {
        "role": args.role,
        "camera_serial": camera["serial"],
        "camera_model": camera["model"],
        "robot_serial": config["follower"]["serial"],
        "base_id": args.base_id,
        "mount_id": args.mount_id,
        "board_mount_id": args.board_mount_id,
        "board": definition,
        "provenance": {
            "source_file": args.source.name,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "split_policy": "every-sixth-before-new-capture",
            "path_clearance_verified": False,
        },
    }
    document = importing.convert(yaml.safe_load(raw), context, config["limits"])
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects previous imported evidence from replacement.
    with output.with_suffix(".source.yaml").open("xb") as stream:
        stream.write(raw)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, allow_nan=False) + "\n")
    preview = deployment.preview(
        routes.parse(document, args.role, config["limits"]), config["limits"]
    )
    filesystem.write_json(output.with_suffix(".preview.json"), preview)
    print(json.dumps(preview, indent=2))


if __name__ == "__main__":
    main()
