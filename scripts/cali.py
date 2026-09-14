"""Launch the calibration owner without a leader device or gripper targets."""

import os
import pathlib
import subprocess
import sys

import teleop

from ur12e_collection.calibration import commands


def launch(args):
    """Offline work stays local; physical work uses the current Ubuntu image."""
    args.config = args.config or teleop.ROOT / "config/teleop.ur.json"
    args.station = (
        args.station or teleop.ROOT / "config/local/recording.station.json"
    )
    if args.solve or args.verify or args.validate_only:
        return commands.run(args)
    if not args.operator_approved or sys.platform != "linux":
        raise ValueError(
            "replay requires Ubuntu and explicit --operator-approved"
        )
    if args.poses is None or args.output is None:
        raise ValueError("replay requires --poses FILE and --output RUN")
    # File preflight happens before Docker starts or any device is opened.
    # pylint: disable-next=import-outside-toplevel
    from ur12e_collection.calibration import replay

    config, _ = replay.prepare(args)
    paths = {
        name: getattr(args, name).expanduser().resolve()
        for name in ("config", "station", "poses", "output")
    }
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
    output = paths["output"].parent
    command += [
        "-v",
        f"{output}:{output}:rw",
        "--entrypoint",
        "python",
        image,
        "-m",
        "ur12e_collection",
        "cali",
        "--" + args.role.replace("third_", ""),
        "--operator-approved",
    ]
    for name, path in paths.items():
        command += ["--" + name, str(path)]
    return subprocess.run(command, check=False).returncode
