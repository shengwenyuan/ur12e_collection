"""Launch native PC teleoperation with restricted USB and no network access."""

import argparse
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# pylint: disable-next=wrong-import-position
from ur12e_collection.followers import config


def main():
    """Keep scene, IPC and configuration paths identical across namespaces."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--image", default="ur12e-collection:native-isaac")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("teleoperation runs on the Ubuntu PC")
    path = args.config.expanduser().resolve()
    value = config.load(path)
    device = pathlib.Path(value["leader"]["device"]).resolve(strict=True)
    mounts = {ROOT: "ro", value["scene"]["root"]: "ro", path.parent: "ro"}
    for follower in [value["follower"], *value.get("twins", [])]:
        parent = follower["endpoint"].parent
        parent.mkdir(parents=True, exist_ok=True)
        mounts[parent] = "rw"
    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "-it",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "1g",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--group-add",
        str(device.stat().st_gid),
        "--device",
        f"{device}:{value['leader']['device']}:rw",
        "--tmpfs",
        "/tmp:rw,nosuid,size=64m",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
    ]
    for location, mode in mounts.items():
        command += ["-v", f"{location}:{location}:{mode}"]
    command += [
        "--entrypoint",
        "python",
        args.image,
        "-m",
        "ur12e_collection",
        "teleop",
        "--config",
        str(path),
    ]
    raise SystemExit(subprocess.run(command, check=False).returncode)


if __name__ == "__main__":
    main()
