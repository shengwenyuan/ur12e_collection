#!/usr/bin/env python3
"""Start daily collection using the provisioned PC deployment."""

import argparse
import pathlib

import teleop
import cali

from ur12e_collection import task_routes
from ur12e_collection.calibration import commands


def choose_task(routes):
    """Select once per session, before the shared launcher touches hardware."""
    choices = list(routes.items())
    print("Collection mode: GELLO\nTasks:", flush=True)
    for number, (description, directory) in enumerate(choices, 1):
        print(f"  {number}. {description}\n     Directory: {directory}")
    while True:
        try:
            answer = input("Task number (q exits): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCollection cancelled.", flush=True)
            raise SystemExit(0) from None
        if answer == "q":
            raise SystemExit(0)
        if (
            answer.isascii()
            and answer.isdigit()
            and 1 <= int(answer) <= len(choices)
        ):
            return choices[int(answer) - 1]
        print("Choose one of the displayed task numbers.", flush=True)


def main(argv=None):
    """Translate an operator command into the shared recording launcher."""
    parser = argparse.ArgumentParser(prog="ur12e", description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    gello = modes.add_parser(
        "gello", help="start GELLO collection; Space controls HOME/start/stop"
    )
    gello.add_argument(
        "--task-routes",
        type=pathlib.Path,
        default=teleop.ROOT / "config/task-routes.json",
        help="task description to directory JSON (default: deployment config)",
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
    configuration = teleop.ROOT / "config/local/teleop.ur.json"
    if not configuration.exists():
        configuration = teleop.ROOT / "config/teleop.ur.json"
    station = teleop.ROOT / "config/local/recording.station.json"
    for path in (configuration, station):
        if not path.is_file():
            parser.error(f"missing station configuration: {path}")
    try:
        routes = task_routes.load(args.task_routes.expanduser().resolve())
    except (OSError, ValueError) as error:
        parser.error(f"invalid task routes: {error}")
    description, directory = choose_task(routes)
    output = args.output.expanduser().resolve() / directory
    print(f"Task: {description}\nOutput: {output}", flush=True)
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
            str(output),
            "--task",
            description,
        ]
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
