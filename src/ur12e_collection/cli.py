"""Explicit collection commands; unfinished device workflows fail closed."""

import argparse
import json
import pathlib
import sys

import jsonschema

import ur12e_collection
from ur12e_collection import cameras
from ur12e_collection import diagnostics
from ur12e_collection import station
from ur12e_collection import ur


def parser() -> argparse.ArgumentParser:
    """Construct commands without device imports or connections."""
    root = argparse.ArgumentParser(prog="ur-collect")
    root.add_argument(
        "--version", action="version", version=ur12e_collection.version()
    )
    commands = root.add_subparsers(dest="command")
    doctor = commands.add_parser(
        "doctor", help="inspect software and mounts only"
    )
    doctor.add_argument("--format", choices=("json", "text"), default="text")
    doctor.add_argument(
        "--backend", choices=("fake", "hardware"), default="fake"
    )
    doctor.add_argument(
        "--config-dir", type=pathlib.Path, default=pathlib.Path("/config")
    )
    doctor.add_argument(
        "--data-dir", type=pathlib.Path, default=pathlib.Path("/data")
    )
    doctor.add_argument("--require-mounts", action="store_true")
    station_commands = commands.add_parser("station").add_subparsers(
        dest="operation"
    )
    initialize = station_commands.add_parser(
        "initialize", help="create an incomplete draft only"
    )
    initialize.add_argument("--output", type=pathlib.Path, required=True)
    validate = station_commands.add_parser(
        "validate", help="validate a station JSON document"
    )
    validate.add_argument("path", type=pathlib.Path)
    validate.add_argument("--cameras-ready", action="store_true")
    devices = commands.add_parser("devices").add_subparsers(dest="device")
    camera = devices.add_parser(
        "cameras", help="explicit RealSense inventory or short capture"
    )
    camera.add_argument("--seconds", type=float, default=0)
    camera.add_argument("--output", type=pathlib.Path)
    camera.add_argument("--serial", action="append", default=[])
    robot = devices.add_parser("ur", help="bounded read-only UR diagnostic")
    robot.add_argument("--host", required=True)
    robot.add_argument("--seconds", type=float, default=2)
    robot.add_argument("--output", type=pathlib.Path, required=True)
    episodes = commands.add_parser("episode").add_subparsers(dest="operation")
    verify = episodes.add_parser(
        "verify", help="decode and check a local episode"
    )
    verify.add_argument("path", type=pathlib.Path)
    shadow = commands.add_parser(
        "shadow", help="camera-only batch; no robot motion"
    )
    shadow.add_argument(
        "--backend", choices=("hardware", "synthetic"), required=True
    )
    shadow.add_argument("--station", type=pathlib.Path)
    shadow.add_argument(
        "--read-feedback",
        action="store_true",
        help="observe UR and Hand-E only; never send control",
    )
    shadow.add_argument("--output", type=pathlib.Path, required=True)
    shadow.add_argument("--revision", required=True)
    shadow.add_argument("--task", default="camera-shadow")
    shadow.add_argument("--episodes", type=int, default=20)
    shadow.add_argument("--seconds", type=float, default=40)
    for command in ("session", "calibrate"):
        commands.add_parser(
            command, help="unavailable: owning module not implemented"
        )
    return root


def _doctor(args: argparse.Namespace) -> int:
    result = diagnostics.report(args.backend, args.config_dir, args.data_dir)
    required = (
        ("jsonschema",)
        if args.backend == "fake"
        else tuple(diagnostics.DEPENDENCIES)
    )
    healthy = all(
        result["dependencies"][name]["state"] == "available"
        for name in required
    )
    if args.require_mounts:
        healthy &= all(
            value["state"] == "available" for value in result["mounts"].values()
        )
    result["software_ready"] = healthy
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(
            f"ur-collect {result['version']}: backend={args.backend}, "
            f"software_ready={healthy}"
        )
        print("Hardware not checked; motion readiness is false.")
        for name, value in result["dependencies"].items():
            print(f"  {name}: {value['state']}")
    return 0 if healthy else 1


def _devices(args: argparse.Namespace) -> int:
    if args.device == "cameras":
        result = cameras.probe(args.seconds, args.output, args.serial)
        passed = all(c["state"] == "passed" for c in result["captures"])
    elif args.device == "ur":
        result = ur.probe(args.host, args.seconds, args.output)
        passed = result["rtde"]["state"] == "available"
    else:
        raise ValueError("a device operation is required")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


def _station(args: argparse.Namespace) -> int:
    if args.operation == "initialize":
        station.write(args.output, station.example())
        print("Created incomplete station draft; motion remains disabled.")
        return 0
    if args.operation == "validate":
        station.load(args.path, cameras_ready=args.cameras_ready)
        print("Station structure valid; hardware and motion are not verified.")
        return 0
    raise ValueError("a station operation is required")


def main(argv: list[str] | None = None) -> int:
    """Run one explicitly requested operation, returning a process exit code."""
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.command is None:
            root.print_help()
            return 0
        handler = {
            "doctor": _doctor,
            "devices": _devices,
            "station": _station,
            "episode": _episode,
            "shadow": _shadow,
        }.get(args.command)
        if handler is not None:
            return handler(args)
    except (
        ImportError,
        OSError,
        RuntimeError,
        ValueError,
        jsonschema.ValidationError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        "error: command unavailable; no hardware action performed",
        file=sys.stderr,
    )
    return 2


def _episode(args: argparse.Namespace) -> int:
    # Optional codec dependencies are loaded only for explicit episode commands.
    # pylint: disable-next=import-outside-toplevel
    from ur12e_collection import storage

    if args.operation != "verify":
        raise ValueError("an episode operation is required")
    print(json.dumps(storage.verify_episode(args.path), indent=2))
    return 0


def _shadow(args: argparse.Namespace) -> int:
    # Explicit command only: importing the CLI cannot start a camera source.
    # pylint: disable-next=import-outside-toplevel
    from ur12e_collection import shadow

    try:
        result = shadow.run(
            shadow.Options(
                backend=args.backend,
                output=args.output,
                revision=args.revision,
                task=args.task,
                episodes=args.episodes,
                seconds=args.seconds,
                station_path=args.station,
                read_feedback=args.read_feedback,
            )
        )
    except KeyboardInterrupt:
        return 130
    print(
        json.dumps(
            {
                "state": result["state"],
                "episodes": len(result["episodes"]),
                "report": str(args.output / "report.json"),
            },
            indent=2,
        )
    )
    return 0
