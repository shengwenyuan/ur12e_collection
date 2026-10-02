"""Camera-specific replay, offline solve and verification entrypoints."""

import json
import pathlib


def configure(parser):
    """Parsing/help never opens devices or imports an SDK."""
    cameras = parser.add_mutually_exclusive_group(required=True)
    for flag, role in (
        ("left", "third_left"),
        ("right", "third_right"),
        ("wrist", "wrist"),
    ):
        cameras.add_argument(
            f"--{flag}", dest="role", action="store_const", const=role
        )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--validate", action="store_true", help="offline checks only"
    )
    mode.add_argument(
        "--replay",
        action="store_true",
        help="authorize route motion and capture",
    )
    mode.add_argument("--activate", type=pathlib.Path, metavar="BUNDLE")
    evidence = parser.add_mutually_exclusive_group()
    evidence.add_argument("--solve", type=pathlib.Path, metavar="RUN")
    evidence.add_argument("--verify", type=pathlib.Path, metavar="BUNDLE")
    parser.add_argument("--calibration-config", type=pathlib.Path)
    parser.add_argument("--poses", type=pathlib.Path)
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--station", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--result-output", type=pathlib.Path)


def check_mode(args):
    """Reject incompatible operations before file, network or device access."""
    if sum((args.replay, args.validate, bool(args.activate))) != 1:
        raise ValueError("select --replay, --validate or --activate")
    if (args.solve or args.verify) and not args.validate:
        raise ValueError("--solve and --verify require --validate")


def _execute(args):
    """Offline operations never enter the physical replay lifecycle."""
    # Optional vision/motion dependencies only load for the selected operation.
    # pylint: disable=import-outside-toplevel
    if args.activate:
        from ur12e_collection.calibration import activation

        if args.station is None:
            raise ValueError("activation requires --station")
        value = activation.activate(args.activate, args.station, args.role)
    elif args.solve or args.verify:
        from ur12e_collection.calibration import pipeline

        selected = args.solve or args.verify
        document = json.loads(
            (selected / "run.json").read_text(encoding="utf-8")
        )
        if document["route"]["role"] != args.role:
            raise ValueError("selected camera differs from the evidence role")
        if args.solve and args.output is None:
            raise ValueError("--solve requires --output BUNDLE")
        value = (
            pipeline.solve(args.solve, args.output)
            if args.solve
            else pipeline.verify(args.verify)
        )
    else:
        from ur12e_collection.calibration import replay

        if not all((args.poses, args.config, args.station)):
            raise ValueError(
                "replay/validation requires --poses, --config and --station"
            )
        if args.replay and args.output is None:
            raise ValueError("replay requires --output RUN")
        result_path = None
        if args.replay:
            result_path = args.result_output or (
                args.output.with_name(args.output.name + ".result")
            )
            for path in (
                result_path,
                result_path.with_name(result_path.name + ".partial"),
            ):
                if path.exists():
                    raise FileExistsError(path)
        value = replay.run(args)
        if result_path:
            from ur12e_collection.calibration import pipeline

            result = pipeline.solve(args.output, result_path)
            value.update(
                result=str(result_path), calibration_id=result["calibration_id"]
            )
    print(json.dumps(value, indent=2))
    return 0


def run(args):
    """Report invalid input as a CLI error, including OpenCV fit failures."""
    check_mode(args)
    # pylint: disable=import-outside-toplevel
    import cv2
    from ur12e_collection.calibration import deployment

    try:
        deployment.configure(args)
        return _execute(args)
    # OpenCV exports its exception through the native extension.
    # pylint: disable-next=catching-non-exception
    except (KeyError, TypeError, cv2.error) as error:
        raise ValueError(f"invalid calibration input: {error}") from error
