"""Offline calibration commands; argument parsing never imports motion code."""

import argparse
import json
import pathlib


def configure(parser: argparse.ArgumentParser) -> None:
    """Expose explicit solve, verification, setup declaration and activation."""
    commands = parser.add_subparsers(dest="operation", required=True)
    solve = commands.add_parser(
        "solve", help="solve a local observation manifest"
    )
    solve.add_argument("input", type=pathlib.Path)
    solve.add_argument("--output", type=pathlib.Path, required=True)
    verify = commands.add_parser(
        "verify", help="recheck a completed result bundle"
    )
    verify.add_argument("bundle", type=pathlib.Path)
    activate = commands.add_parser(
        "activate", help="activate a matching result"
    )
    activate.add_argument("bundle", type=pathlib.Path)
    activate.add_argument("--station", type=pathlib.Path, required=True)
    setup = commands.add_parser(
        "setup", help="declare mounts and invalidate changes"
    )
    setup.add_argument("--station", type=pathlib.Path, required=True)
    setup.add_argument("--input", type=pathlib.Path, required=True)
    reference = commands.add_parser(
        "leader-reference", help="summarize a stable local encoder trace"
    )
    reference.add_argument("input", type=pathlib.Path)
    reference.add_argument("--output", type=pathlib.Path, required=True)
    leader = commands.add_parser(
        "leader-validate", help="validate joint calibration without hardware"
    )
    leader.add_argument("input", type=pathlib.Path)


def run(args: argparse.Namespace) -> int:
    """Run local filesystem and OpenCV work only after explicit selection."""
    if args.operation.startswith("leader-"):
        return _leader(args)
    # Optional calibration dependencies do not belong in general CLI startup.
    # pylint: disable=import-outside-toplevel
    import cv2
    from ur12e_collection.calibration import results

    try:
        if args.operation == "solve":
            value = results.solve(args.input, args.output)
        elif args.operation == "verify":
            value = results.verify(args.bundle)
        elif args.operation == "activate":
            value = results.activate(args.bundle, args.station)
        else:
            value = results.declare(
                args.station, json.loads(args.input.read_text(encoding="utf-8"))
            )
    # OpenCV exports its exception through the native extension.
    # pylint: disable-next=catching-non-exception
    except (KeyError, TypeError, cv2.error) as error:
        raise ValueError(f"invalid calibration input: {error}") from error
    print(json.dumps(value, indent=2))
    return 0


def _leader(args: argparse.Namespace) -> int:
    # No SDK, serial device or robot controller is imported by calibration.
    # pylint: disable-next=import-outside-toplevel
    from ur12e_collection.leader import mapping

    if args.operation == "leader-reference":
        value = mapping.reference(args.input)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2) + "\n")
    else:
        calibration = mapping.load(args.input)
        value = {
            "state": "valid_structure",
            "physical_alignment": "not_checked",
            "motion_ready": False,
            "reference": calibration.reference,
            "calibration_id": calibration.identity(),
        }
    print(json.dumps(value, indent=2))
    return 0
