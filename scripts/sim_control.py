"""Run control checks in an isolated, verified local URSim network."""

import argparse
import json
import os
import pathlib
import subprocess
import tempfile
import time

import sim_program
import sim_source

ROOT = pathlib.Path(__file__).resolve().parents[1]
NETWORK = "ur12e-sim_control"
SIMULATOR = "ur12e-sim-ursim-1"
IMAGE = (
    "universalrobots/ursim_e-series@sha256:"
    "39909bad9a8247980a1c9144da322ff7c4d34db0e89870f4c6b4dabd7c55c95d"
)


def inspect(kind: str, name: str) -> dict:
    """Read Docker facts; never infer identity from a user-supplied address."""
    result = subprocess.run(
        ["docker", kind, "inspect", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)[0]


def main() -> None:
    """Launch only supported test entrypoints with no station or host option."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "motion",
            "watchdog",
            "native-home",
            "prepare-home",
            "home",
            "session",
            "session-faults",
            "console",
        ),
    )
    parser.add_argument("--signal", choices=("kill", "stall"), default="kill")
    parser.add_argument(
        "--client-image",
        default=os.environ.get("UR12E_IMAGE", "ur12e-collection:current"),
    )
    parser.add_argument("--episodes", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--ros-observe", action="store_true")
    parser.add_argument("--kill-observer", action="store_true")
    args = parser.parse_args()
    if args.ros_observe and args.mode not in ("session", "console"):
        parser.error("ROS observation requires session or console mode")
    if args.kill_observer and (args.mode != "session" or not args.ros_observe):
        parser.error("observer kill test requires session --ros-observe")
    client = inspect("image", args.client_image)
    if (client["Os"], client["Architecture"]) != ("linux", "amd64"):
        raise ValueError("simulator client requires a local linux/amd64 image")
    sim = inspect("container", SIMULATOR)
    image = inspect("image", IMAGE)
    network = inspect("network", NETWORK)
    labels = sim["Config"]["Labels"]
    if (
        sim["Image"] != image["Id"]
        or labels.get("com.docker.compose.project") != "ur12e-sim"
        or labels.get("com.docker.compose.service") != "ursim"
        or not sim["State"]["Running"]
        or not network["Internal"]
    ):
        raise RuntimeError(
            "local simulator image/service/network is unverified"
        )
    peer = sim["NetworkSettings"]["Networks"][NETWORK]
    if "ursim-control" not in peer["Aliases"]:
        raise RuntimeError("simulator control alias is missing")
    home = (
        sim_program.prepare(SIMULATOR)
        if args.mode
        in ("prepare-home", "home", "session", "session-faults", "console")
        else None
    )
    if args.mode == "prepare-home":
        print(json.dumps(home, indent=2))
        return
    output = ROOT / "artifacts/simulator-control"
    output.mkdir(parents=True, exist_ok=True)
    lock = output / "lock"
    lock.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="permit-", dir=output) as temporary:
        frozen = sim_source.freeze(ROOT, pathlib.Path(temporary))
        frozen["client_image"] = client["Id"]
        frozen["source_revision"] += (
            "-image-" + client["Id"].split(":")[-1][:12]
        )
        (output / (frozen["source_revision"] + ".json")).write_text(
            json.dumps(frozen, indent=2), encoding="utf-8"
        )
        permit = pathlib.Path(temporary) / "permit.json"
        permit.write_text(
            json.dumps(
                {
                    **frozen,
                    "image": IMAGE,
                    "host": "ursim-control",
                    "address": peer["IPAddress"],
                    "home": home,
                }
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--pull",
                "never",
                "--init",
                *(["--interactive", "--tty"] if args.mode == "console" else []),
                "--platform",
                "linux/amd64",
                "--network",
                NETWORK,
                "--memory",
                "2g",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,nosuid,size=128m",
                "-v",
                f"{temporary}/src:/workspace/src:ro",
                "-v",
                f"{temporary}/checks:/checks:ro",
                "-v",
                f"{permit}:/sim-permit.json:ro",
                "-v",
                f"{lock}:/sim-lock:rw",
                "-v",
                f"{output}:/results:rw",
                "-e",
                "PYTHONPATH=/workspace/src",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "--entrypoint",
                "/bin/bash",
                "-e",
                "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST",
                "-e",
                "ROS_LOG_DIR=/tmp/ros-log",
                client["Id"],
                "-c",
                'source /opt/ros/jazzy/setup.bash && exec python "$@"',
                "simulator",
                "-u",
                *_entrypoint(args, frozen["source_revision"]),
            ],
            check=False,
        )
        if args.mode == "console" and completed.returncode == 130:
            raise SystemExit(130)
        completed.check_returncode()


def _entrypoint(args, revision):
    if args.mode == "console":
        return [
            "-m",
            "ur12e_collection",
            "session",
            "--backend",
            "ursim",
            "--output",
            f"/results/console-{time.time_ns()}",
            "--revision",
            revision,
            *(["--ros-observe"] if args.ros_observe else []),
        ]
    return [
        f"/checks/{args.mode.replace('-', '_')}.py",
        *([args.signal] if args.mode == "watchdog" else []),
        *(["--ros-observe"] if args.ros_observe else []),
        *(["--kill-observer"] if args.kill_observer else []),
        *(
            ["--episodes", str(args.episodes), "--seconds", str(args.seconds)]
            if args.mode == "session"
            else []
        ),
    ]


if __name__ == "__main__":
    main()
