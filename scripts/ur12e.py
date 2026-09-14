#!/usr/bin/env python3
"""Start daily collection using the provisioned PC deployment."""

import argparse
import pathlib

import teleop
import cali

from ur12e_collection.calibration import commands


def main(argv=None):
    """Translate an operator command into the shared recording launcher."""
    parser = argparse.ArgumentParser(prog="ur12e", description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    gello = modes.add_parser(
        "gello", help="start GELLO collection; Space controls HOME/start/stop"
    )
    gello.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path.home() / "ur12e-data",
        help="recording directory (default: ~/ur12e-data)",
    )
    commands.configure(
        modes.add_parser("cali", help="camera calibration replay/solve")
    )
    args = parser.parse_args(argv)
    if args.mode == "cali":
        try:
            return cali.launch(args)
        except (ValueError, OSError) as error:
            parser.error(str(error))
    configuration = teleop.ROOT / "config/teleop.ur.json"
    station = teleop.ROOT / "config/local/recording.station.json"
    for path in (configuration, station):
        if not path.is_file():
            parser.error(f"missing station configuration: {path}")
    teleop.main(
        [
            "--config",
            str(configuration),
            "--image",
            "ur12e-collection:current",
            "--operator-approved",
            "--record-station",
            str(station),
            "--record-output",
            str(args.output.expanduser().resolve()),
            "--task",
            "gello_collection",
        ]
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
