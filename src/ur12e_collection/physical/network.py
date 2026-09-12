"""Verify local Ethernet routing without sending robot control messages."""

import fcntl
import ipaddress
import pathlib
import socket
import struct
import subprocess
import sys


# Decode one Linux routing snapshot and its interface attributes together.
# pylint: disable=too-many-locals
def route(host, interface, root=pathlib.Path("/")):
    """Require the most specific IPv4 route to be direct physical Ethernet."""
    if sys.platform != "linux":
        raise ValueError("physical teleoperation requires the Linux station")
    address = ipaddress.IPv4Address(host)
    candidates = []
    for line in (root / "proc/net/route").read_text().splitlines()[1:]:
        fields = line.split()
        destination, gateway, flags, mask = (
            int(fields[i], 16) for i in (1, 2, 3, 7)
        )
        target = int.from_bytes(address.packed, "little")
        if flags & 1 and target & mask == destination:
            candidates.append((mask.bit_count(), fields[0], gateway))
    if not candidates:
        raise ValueError("no local route to the robot")
    _, device, gateway = max(candidates)
    base = root / "sys/class/net" / device
    if gateway or device != interface or (base / "wireless").exists():
        raise ValueError("robot requires direct wired Ethernet, no gateway")
    if (
        not (base / "device").exists()
        or (base / "type").read_text().strip() != "1"
        or (base / "carrier").read_text().strip() != "1"
    ):
        raise ValueError("robot requires direct wired Ethernet, no gateway")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        # UDP connect selects a route; it sends no datagram.
        probe.connect((host, 30004))
        source = probe.getsockname()[0]
        request = struct.pack("256s", device.encode()[:15])
        local = socket.inet_ntoa(fcntl.ioctl(probe, 0x8915, request)[20:24])
        mask = socket.inet_ntoa(fcntl.ioctl(probe, 0x891B, request)[20:24])
    if source != local or address not in ipaddress.IPv4Network(
        f"{local}/{mask}", strict=False
    ):
        raise ValueError("robot is not on the selected local Ethernet subnet")
    return {
        "host": host,
        "interface": device,
        "source": source,
        "gateway": None,
    }


def check(host, interface):
    """Perform host-side route and bounded loss check before Docker startup."""
    result = route(host, interface)
    completed = subprocess.run(
        [
            "ping",
            "-n",
            "-I",
            interface,
            "-c",
            "5",
            "-i",
            "0.2",
            "-W",
            "1",
            host,
        ],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    )
    # Match the complete percentage field, not the suffix of 100%.
    if completed.returncode or ", 0% packet loss" not in completed.stdout:
        raise ValueError("wired robot ping failed or lost packets")
    return result | {"ping": completed.stdout.strip()}
