"""Daily operator commands executed directly in the collector container."""

import argparse
import os
import pathlib

from ur12e_collection import cli, task_routes
from ur12e_collection.calibration import commands
from ur12e_collection.followers import config as configuration
from ur12e_collection.physical import network


def choose_task(routes: dict[str, str]) -> tuple[str, str]:
    """Select once per session before any hardware resources are opened."""
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
        print("Choose one of the displayed task numbers.")


def parser() -> argparse.ArgumentParser:
    """Describe mounted configuration and data without opening devices."""
    config = pathlib.Path(os.environ.get("UR12E_CONFIG_DIR", "/config"))
    routes = config / "task-routes.json"
    if not routes.exists():
        routes = pathlib.Path("/opt/examples/task-routes.json")
    root = argparse.ArgumentParser(
        prog="ur12e", description="Collect and calibrate from this terminal."
    )
    modes = root.add_subparsers(dest="mode", required=True)
    gello = modes.add_parser(
        "gello", help="GELLO collection; Space HOME/start/stop"
    )
    gello.add_argument(
        "--config", type=pathlib.Path, default=config / "teleop.ur.json"
    )
    gello.add_argument(
        "--station",
        type=pathlib.Path,
        default=config / "recording.station.json",
    )
    gello.add_argument("--task-routes", type=pathlib.Path, default=routes)
    gello.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path(os.environ.get("UR12E_DATA_DIR", "/data")),
    )
    cali = modes.add_parser("cali", help="camera calibration replay/solve")
    commands.configure(cali)
    cali.set_defaults(
        config=config / "teleop.ur.json",
        station=config / "recording.station.json",
    )
    return root


def main(argv: list[str] | None = None) -> int:
    """Reuse the existing session owner without starting another container."""
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.mode == "cali":
            return commands.run(args)
        for path in (args.config, args.station):
            if not path.expanduser().is_file():
                root.error(f"missing station configuration: {path}")
        routes = task_routes.load(args.task_routes.expanduser().resolve())
        description, directory = choose_task(routes)
        output = args.output.expanduser().resolve() / directory
        print(f"Task: {description}\nOutput: {output}", flush=True)
        profile = configuration.load(args.config)
        if profile["follower"]["backend"] != "ur":
            raise ValueError("GELLO collection requires a physical UR profile")
        print(
            network.check(
                profile["follower"]["host"], profile["follower"]["interface"]
            ),
            flush=True,
        )
        return cli.main(
            [
                "teleop",
                "--config",
                str(args.config.expanduser().resolve()),
                "--operator-approved",
                "--record-station",
                str(args.station.expanduser().resolve()),
                "--record-output",
                str(output),
                "--task",
                description,
            ]
        )
    except (OSError, ValueError) as error:
        root.error(str(error))
    return 2
