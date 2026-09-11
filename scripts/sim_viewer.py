#!/usr/bin/env python3
"""Independent loopback 3D window for actual URSim feedback; no motion API."""

import argparse
import functools
import http.server
import json
import math
import pathlib
import subprocess
import tempfile
import threading
import time
import uuid

import sim_control

FILES = pathlib.Path(__file__).with_suffix("")
ASSETS = FILES / "assets"
STALE_SECONDS = 1.0
ASSET_TYPES = {
    "/": ("index.html", "text/html"),
    "/viewer.js": ("viewer.js", "text/javascript"),
    "/kinematics.js": ("kinematics.js", "text/javascript"),
    "/three.module.min.js": ("three.module.min.js", "text/javascript"),
    "/three.core.min.js": ("three.core.min.js", "text/javascript"),
}


class State:
    """Track controller progress separately from message receipt."""

    def __init__(self):
        self.lock = threading.Lock()
        self.value = None
        self.received = self.progress = 0.0
        self.error = "Waiting for URSim actual joint angles"

    def accept(self, value, now):
        """Reject malformed, nonfinite or regressed observations."""
        q, stamp = value.get("actual_q"), value.get("timestamp_s")
        numbers = q + [stamp] if isinstance(q, list) and len(q) == 6 else []
        if (
            not numbers
            or any(
                type(v) not in (float, int) or not math.isfinite(v)
                for v in numbers
            )
            or stamp < 0
        ):
            raise ValueError("invalid actual joint state")
        with self.lock:
            if self.value is not None:
                previous = self.value["timestamp_s"]
                if stamp < previous or (
                    stamp == previous and q != self.value["actual_q"]
                ):
                    raise ValueError(
                        "controller state changed without advancing time"
                    )
            if self.value is None or stamp > self.value["timestamp_s"]:
                self.progress = now
            self.value = {"actual_q": q, "timestamp_s": stamp}
            self.received, self.error = now, None

    def fail(self, error):
        """Retain the last pose while marking the source unavailable."""
        with self.lock:
            self.error = str(error)

    def snapshot(self, now):
        """Age frozen timestamps even when repeated messages still arrive."""
        with self.lock:
            age = max(now - self.received, now - self.progress)
            fresh = (
                self.value is not None
                and self.error is None
                and age <= STALE_SECONDS
            )
            return {
                **(self.value or {}),
                "fresh": fresh,
                "age_ms": round(age * 1000) if self.value else None,
                "error": self.error
                or (None if fresh else "URSim state is stale"),
            }


def consume(stream, state):
    """Read bounded JSON lines from this viewer's receive-only child."""
    try:
        while line := stream.readline(16385):
            if len(line) > 16384:
                raise ValueError("oversized viewer observation")
            state.accept(json.loads(line), time.monotonic())
        raise EOFError("URSim reader disconnected")
    except (ValueError, TypeError, AttributeError, EOFError) as error:
        state.fail(error)


class Handler(http.server.BaseHTTPRequestHandler):
    """Serve an exact read-only allowlist, never arbitrary files or commands."""

    def __init__(self, *args, state, **kwargs):
        self.state = state
        super().__init__(*args, **kwargs)

    def do_GET(self):  # pylint: disable=invalid-name
        """Serve local viewer assets or the current measured state."""
        if self.path == "/state":
            payload = json.dumps(self.state.snapshot(time.monotonic())).encode()
            content_type = "application/json"
        elif self.path in ASSET_TYPES:
            name, content_type = ASSET_TYPES[self.path]
            payload = (ASSETS / name).read_bytes()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


def reader_command(image, permit, name):
    """No USB mounts, published ports, control lease or robot initialization."""
    return [
        "docker",
        "run",
        "--rm",
        "--init",
        "--name",
        name,
        "--pull",
        "never",
        "--platform",
        "linux/amd64",
        "--network",
        sim_control.NETWORK,
        "--memory",
        "384m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,size=16m",
        "-v",
        f"{permit}:/sim-permit.json:ro",
        "-v",
        f"{FILES / 'reader.py'}:/viewer-reader.py:ro",
        "--entrypoint",
        "python",
        image,
        "-u",
        "/viewer-reader.py",
    ]


def main():
    """Run independently beside the existing live-leader console."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--client-image", default="ur12e-collection:live-leader"
    )
    args = parser.parse_args()
    peer = sim_control.verified_peer()
    image = sim_control.inspect("image", args.client_image)
    if (image["Os"], image["Architecture"]) != ("linux", "amd64"):
        parser.error("viewer reader requires the existing linux/amd64 image")
    state = State()
    handler = functools.partial(Handler, state=state)
    with (
        http.server.ThreadingHTTPServer(
            ("127.0.0.1", args.port), handler
        ) as server,
        tempfile.TemporaryDirectory(prefix="ursim-viewer-") as temporary,
    ):
        permit = pathlib.Path(temporary) / "permit.json"
        permit.write_text(
            json.dumps(
                {
                    "image": sim_control.IMAGE,
                    "host": "ursim-control",
                    "address": peer["IPAddress"],
                }
            ),
            encoding="utf-8",
        )
        name = "ur12e-viewer-" + uuid.uuid4().hex[:10]
        # The finally block also removes the reader container on interruption.
        # pylint: disable-next=consider-using-with
        process = subprocess.Popen(
            reader_command(image["Id"], permit, name),
            stdout=subprocess.PIPE,
            text=True,
        )
        worker = threading.Thread(
            target=consume, args=(process.stdout, state), daemon=True
        )
        worker.start()
        print(
            f"Read-only 3D viewer: http://127.0.0.1:{server.server_port}",
            flush=True,
        )
        print(
            "Ctrl+C closes only the viewer. Robot control is unchanged.",
            flush=True,
        )
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name], capture_output=True, check=False
            )
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            worker.join(timeout=2)
            process.stdout.close()


if __name__ == "__main__":
    main()
