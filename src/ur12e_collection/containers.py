"""Host-only Docker command assembly; importing this module opens no devices."""

import os
import pathlib
import subprocess


def container_command(
    image_name: str, memory: str, *, physical: bool, interactive: bool = True
) -> tuple[list[str], str]:
    """Pin the local image and share restrictions across host launchers."""
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


def camera_devices(
    root: pathlib.Path = pathlib.Path("/sys/class/video4linux"),
) -> list[str]:
    """Expose the USB bus and only RealSense V4L2 nodes as before."""
    devices = ["--device", "/dev/bus/usb"]
    for entry in sorted(root.glob("video*")):
        name = entry / "name"
        if name.is_file() and "RealSense" in name.read_text(encoding="utf-8"):
            devices += ["--device", f"/dev/{entry.name}"]
    return devices
