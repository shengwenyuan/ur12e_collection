"""Launch the calibration owner without a leader device or gripper targets."""

import os
import pathlib
import subprocess
import sys

import teleop

from ur12e_collection.calibration import commands, deployment
from ur12e_collection.physical import network


def launch(args):
    """Offline work stays local; physical work uses the current Ubuntu image."""
    commands.check_mode(args)
    local = teleop.ROOT / "config/local/teleop.ur.json"
    args.config = args.config or (
        local if local.is_file() else teleop.ROOT / "config/teleop.ur.json"
    )
    args.station = (
        args.station or teleop.ROOT / "config/local/recording.station.json"
    )
    local = teleop.ROOT / "config/local/calibration.json"
    if args.calibration_config is None and local.is_file():
        args.calibration_config = local
    deployment.configure(args)
    if not args.replay:
        return _offline(args) if sys.platform == "linux" else commands.run(args)
    if sys.platform != "linux":
        raise ValueError("replay requires the Ubuntu station")
    if args.poses is None or args.output is None:
        raise ValueError("replay requires --poses FILE and --output RUN")
    # File preflight happens before Docker starts or any device is opened.
    # pylint: disable-next=import-outside-toplevel
    from ur12e_collection.calibration import replay

    config, _ = replay.prepare(args)
    print(
        network.check(
            config["follower"]["host"], config["follower"]["interface"]
        ),
        flush=True,
    )
    paths = {
        name: getattr(args, name).expanduser().resolve()
        for name in ("config", "station", "poses", "output")
    }
    if args.result_output is not None:
        paths["result-output"] = args.result_output.expanduser().resolve()
    if (
        paths["output"].exists()
        or paths["output"].with_name(paths["output"].name + ".partial").exists()
    ):
        raise FileExistsError(paths["output"])
    paths["output"].parent.mkdir(parents=True, exist_ok=True)
    lease = (
        pathlib.Path("/tmp")
        / f"ur12e-controller-{config['follower']['serial']}.lock"
    )
    descriptor = os.open(lease, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    command, image = teleop.container_command(
        "ur12e-collection:current", "2g", physical=True
    )
    command += [
        "--shm-size",
        "128m",
        "-e",
        f"UR12E_LEASE={lease}",
        "-e",
        "OPENBLAS_NUM_THREADS=1",
        "-e",
        "OMP_NUM_THREADS=1",
        "-v",
        f"{lease}:{lease}:rw",
    ]
    command += teleop.camera_devices()
    for name in ("config", "station", "poses"):
        command += ["-v", f"{paths[name]}:{paths[name]}:ro"]
    for output in {
        p.parent
        for key, p in paths.items()
        if key in ("output", "result-output")
    }:
        output.mkdir(parents=True, exist_ok=True)
        command += ["-v", f"{output}:{output}:rw"]
    command += [
        "--entrypoint",
        "python",
        image,
        "-m",
        "ur12e_collection",
        "cali",
        "--" + args.role.replace("third_", ""),
        "--replay",
    ]
    for name, path in paths.items():
        command += ["--" + name, str(path)]
    return subprocess.run(command, check=False).returncode


def _offline(args):
    """Use image-pinned OpenCV on the PC, without network or device mounts."""
    command, image = teleop.container_command(
        "ur12e-collection:current", "2g", physical=False, interactive=False
    )
    arguments = ["cali", "--" + args.role.replace("third_", "")]
    names = (
        ("config", "station", "poses")
        if args.validate and not (args.solve or args.verify)
        else ("solve", "verify", "activate")
    )
    if args.activate:
        names += ("station",)
    for name in names:
        selected = getattr(args, name)
        if selected is None:
            continue
        path = selected.expanduser().resolve(strict=True)
        mount = path.parent if args.activate and name == "station" else path
        access = "rw" if args.activate and name == "station" else "ro"
        command += ["-v", f"{mount}:{mount}:{access}"]
        arguments += ["--" + name, str(path)]
    if args.validate:
        arguments += ["--validate"]
    if args.solve:
        if args.output is None:
            raise ValueError("--solve requires --output or calibration config")
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        command += ["-v", f"{output.parent}:{output.parent}:rw"]
        arguments += ["--output", str(output)]
    command += [
        "-e",
        "OPENBLAS_NUM_THREADS=1",
        "-e",
        "OMP_NUM_THREADS=1",
        "--entrypoint",
        "python",
        image,
        "-m",
        "ur12e_collection",
        *arguments,
    ]
    return subprocess.run(command, check=False).returncode
