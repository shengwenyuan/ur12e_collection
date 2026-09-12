"""Launch native PC teleoperation with explicit device and network ownership."""

import argparse
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# Imports follow the explicit repository path bootstrap.
# pylint: disable=wrong-import-position
from ur12e_collection.followers import config
from ur12e_collection.physical import network


def main():
    """Keep scene, IPC and configuration paths identical across namespaces."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--image", default="ur12e-collection:native-isaac")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--operator-approved", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("teleoperation runs on the Ubuntu PC")
    path = args.config.expanduser().resolve()
    value = config.load(path)
    physical = value["follower"]["backend"] == "ur"
    if physical:
        if not (args.preflight or args.operator_approved):
            parser.error("use --preflight or explicit --operator-approved")
        print(
            network.check(
                value["follower"]["host"], value["follower"]["interface"]
            ),
            flush=True,
        )
    device = pathlib.Path(value["leader"]["device"]).resolve(
        strict=not args.preflight
    )
    mounts = {
        ROOT: "ro",
        path.parent: "ro",
        value["leader"]["calibration"].parent: "ro",
    }
    if physical:
        value["evidence"].mkdir(parents=True, exist_ok=True)
        mounts[value["evidence"]] = "rw"
        lease = (
            pathlib.Path("/tmp")
            / f"ur12e-controller-{value['follower']['serial']}.lock"
        )
        descriptor = os.open(
            lease, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        os.close(descriptor)
        mounts[lease] = "rw"
    else:
        mounts[value["scene"]["root"]] = "ro"
    for follower in (
        [] if physical else [value["follower"], *value.get("twins", [])]
    ):
        parent = follower["endpoint"].parent
        parent.mkdir(parents=True, exist_ok=True)
        mounts[parent] = "rw"
    image_id = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", args.image],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "-i" if args.preflight else "-it",
        "--pull",
        "never",
        "--network",
        "host" if physical else "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "1g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,nosuid,size=64m",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        f"UR12E_IMAGE_ID={image_id}",
    ]
    if physical:
        command += ["-e", f"UR12E_LEASE={lease}"]
    if not args.preflight:
        command += [
            "--group-add",
            str(device.stat().st_gid),
            "--device",
            f"{device}:{value['leader']['device']}:rw",
        ]
    for location, mode in mounts.items():
        command += ["-v", f"{location}:{location}:{mode}"]
    command += [
        "--entrypoint",
        "python",
        image_id,
        "-m",
        "ur12e_collection",
        "teleop",
        "--config",
        str(path),
    ]
    if args.preflight:
        command.append("--preflight")
    elif args.operator_approved:
        command.append("--operator-approved")
    raise SystemExit(
        subprocess.run(
            command, check=False, timeout=20 if args.preflight else None
        ).returncode
    )


if __name__ == "__main__":
    main()
