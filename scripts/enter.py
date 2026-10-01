#!/usr/bin/env python3
"""Open the installed collector terminal without starting a hardware session."""

import argparse
import grp
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# The host helper uses only the package's standard-library Docker assembly.
# pylint: disable-next=wrong-import-position
from ur12e_collection import containers


def shell_command(args: argparse.Namespace) -> list[str]:
    """Bind portable station files and the shared existing controller lease."""
    config = args.config_dir.expanduser().resolve(strict=True)
    profile = json.loads(
        (config / "teleop.ur.json").read_text(encoding="utf-8")
    )
    if profile["follower"]["backend"] != "ur":
        raise ValueError("collection terminal requires a physical UR profile")
    data = args.data_dir.expanduser().resolve()
    evidence = args.evidence_dir.expanduser().resolve()
    for directory in (data, evidence):
        directory.mkdir(parents=True, exist_ok=True)
    lease = (
        pathlib.Path("/tmp")
        / f"ur12e-controller-{profile['follower']['serial']}.lock"
    )
    descriptor = os.open(lease, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    command, image = containers.container_command(
        args.image, "8g", physical=True
    )
    command += [
        "--name",
        args.name,
        "--shm-size",
        "512m",
        "-e",
        "UR12E_CONFIG_DIR=/config",
        "-e",
        "UR12E_DATA_DIR=/data",
        "-e",
        "UR12E_LEASE=/run/ur12e-controller.lock",
        "-e",
        "OPENBLAS_NUM_THREADS=1",
        "-e",
        "OMP_NUM_THREADS=1",
        "-e",
        "HOME=/data",
        "-e",
        "HISTFILE=/tmp/.bash_history",
        "-e",
        "PS1=ur12e:\\w\\$ ",
        "-v",
        f"{config}:/config:ro",
        "-v",
        f"{data}:/data:rw",
        "-v",
        f"{evidence}:/evidence:rw",
        "-v",
        f"{lease}:/run/ur12e-controller.lock:rw",
    ]
    groups = set()
    if pathlib.Path("/dev/bus/usb").is_dir():
        command += containers.camera_devices()
        for name in ("video", "plugdev"):
            try:
                groups.add(grp.getgrnam(name).gr_gid)
            except KeyError:
                continue
    leader = pathlib.Path(profile["leader"]["device"]).resolve()
    if leader.exists():
        command += ["--device", f"{leader}:{profile['leader']['device']}:rw"]
        groups.add(leader.stat().st_gid)
    for group in sorted(groups):
        command += ["--group-add", str(group)]
    return command + [
        "--entrypoint",
        "/entrypoint.sh",
        image,
        "bash",
        "--noprofile",
        "--norc",
    ]


def main(argv: list[str] | None = None) -> int:
    """Start only the shell; the operator runs ur12e commands inside it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="ur12e-collection:current")
    parser.add_argument("--name", default="ur12e-collection")
    parser.add_argument(
        "--config-dir", type=pathlib.Path, default=ROOT / "config/local"
    )
    parser.add_argument(
        "--data-dir",
        type=pathlib.Path,
        default=pathlib.Path.home() / "ur12e-data",
    )
    parser.add_argument(
        "--evidence-dir",
        type=pathlib.Path,
        default=ROOT / "artifacts/physical-teleop",
    )
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        parser.error("the collection terminal runs on the Ubuntu station")
    try:
        command = shell_command(args)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
