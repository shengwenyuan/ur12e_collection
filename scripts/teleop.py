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


def arguments(argv=None):
    """Parse the explicit station and recording launch options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--image", default="ur12e-collection:current")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--operator-approved", action="store_true")
    parser.add_argument("--record-station", type=pathlib.Path)
    parser.add_argument("--record-output", type=pathlib.Path)
    parser.add_argument("--task")
    args = parser.parse_args(argv)
    if any((args.record_station, args.record_output, args.task)) and not all(
        (args.record_station, args.record_output, args.task)
    ):
        parser.error("recording requires station, output and task")
    return args, parser


def main(argv=None):
    """Keep scene, IPC and configuration paths identical across namespaces."""
    args, parser = arguments(argv)
    if sys.platform != "linux":
        parser.error("teleoperation runs on the Ubuntu PC")
    path = args.config.expanduser().resolve()
    value = config.load(path)
    physical = value["follower"]["backend"] == "ur"
    recording = bool(args.record_station)
    if recording and (not physical or args.preflight):
        parser.error("recording requires physical teleoperation")
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
    mounts, lease = mount_paths(args, value, path, physical)
    command, image_id = container_command(
        args.image,
        "8g" if recording else "1g",
        physical=physical,
        interactive=not args.preflight,
    )
    if physical:
        command += ["-e", f"UR12E_LEASE={lease}"]
    if recording:
        command += camera_devices() + [
            "--shm-size",
            "512m",
            "-e",
            "OPENBLAS_NUM_THREADS=1",
            "-e",
            "OMP_NUM_THREADS=1",
        ]
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
    if recording:
        command += [
            "--record-station",
            str(args.record_station),
            "--record-output",
            str(args.record_output),
            "--task",
            args.task,
        ]
    raise SystemExit(
        subprocess.run(
            command, check=False, timeout=20 if args.preflight else None
        ).returncode
    )


def container_command(image_name, memory, *, physical, interactive=True):
    """Share image selection and container restrictions across owners."""
    image_id = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image_name],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "-it" if interactive else "-i",
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
        memory,
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,nosuid,size=64m",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-e",
        f"UR12E_IMAGE_ID={image_id}",
    ]
    return command, image_id


def camera_devices(root=pathlib.Path("/sys/class/video4linux")):
    """Expose RealSense V4L2 nodes as required by the existing camera runner."""
    devices = ["--device", "/dev/bus/usb"]
    for entry in sorted(root.glob("video*")):
        name = entry / "name"
        if name.is_file() and "RealSense" in name.read_text(encoding="utf-8"):
            devices += ["--device", f"/dev/{entry.name}"]
    return devices


def mount_paths(args, value, path, physical):
    """Expose only selected configuration, devices and persistent outputs."""
    recording = bool(args.record_station)
    lease = None
    mounts = {
        ROOT: "ro",
        path.parent: "ro",
        value["leader"]["calibration"].parent: "ro",
    }
    if recording:
        args.record_station = args.record_station.expanduser().resolve(
            strict=True
        )
        args.record_output = args.record_output.expanduser().resolve()
        args.record_output.mkdir(parents=True, exist_ok=True)
        mounts[args.record_station.parent] = "ro"
        mounts[args.record_output] = "rw"
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
    return mounts, lease


if __name__ == "__main__":
    main()
