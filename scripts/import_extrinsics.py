#!/usr/bin/env python3
"""Activate a colleague's fixed-camera YAML by serial, without device access."""

import argparse
import pathlib

from ur12e_collection.calibration import external


def main():
    """Keep source paths and station ownership explicit for offline import."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--station", type=pathlib.Path, required=True)
    parser.add_argument("--serial", required=True)
    args = parser.parse_args()
    value = external.activate(args.source, args.station, args.serial)
    for role, result in value["calibration"]["cameras"].items():
        if result["context"]["camera_serial"] == args.serial:
            print(
                f"Activated {args.serial} ({role}): {result['calibration_id']}"
            )


if __name__ == "__main__":
    main()
