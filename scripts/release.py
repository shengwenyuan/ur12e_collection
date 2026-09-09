#!/usr/bin/env python3
"""Package a local image for offline Ubuntu deployment."""

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess


def digest(path: pathlib.Path) -> str:
    """Hash large image archives without loading them into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    """Build a bundle in a new directory; never replace an existing release."""
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        parser.error("release destination or partial directory already exists")
    image = json.loads(
        subprocess.check_output(
            ["docker", "image", "inspect", args.image], text=True
        )
    )[0]
    if (image["Os"], image["Architecture"]) != ("linux", "amd64"):
        parser.error("production bundles require a linux/amd64 image")
    partial.mkdir(parents=True)
    (partial / "scripts").mkdir()
    (partial / "config").mkdir()
    subprocess.run(
        ["docker", "save", "-o", str(partial / "image.tar"), args.image],
        check=True,
    )
    for relative in (
        "compose.yaml",
        "scripts/run",
        "scripts/load-release",
        "scripts/camera-probe",
        "scripts/camera-run",
        "scripts/camera-shadow",
        "config/station.example.json",
    ):
        shutil.copy2(root / relative, partial / relative)
    shutil.copy2(
        root / "docs/m01-runtime-deployment/quickstart.md",
        partial / "README.md",
    )
    shutil.copy2(
        root / "docs/m13-acceptance/lab-runbook.md", partial / "LAB-RUNBOOK.md"
    )
    manifest = {
        "schema_version": 1,
        "image_id": image["Id"],
        "image_tag": args.image,
        "platform": f"{image['Os']}/{image['Architecture']}",
        "source_revision": image["Config"]
        .get("Labels", {})
        .get("org.opencontainers.image.revision", "unknown"),
        "base_image": image["Config"]
        .get("Labels", {})
        .get("org.opencontainers.image.base.name", "unknown"),
    }
    for filename in ("os-packages.txt", "python-packages.txt"):
        data = subprocess.check_output(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "cat",
                image["Id"],
                f"/opt/{filename}",
            ]
        )
        (partial / filename).write_bytes(data)
    (partial / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    files = sorted(path for path in partial.rglob("*") if path.is_file())
    checksums = "".join(
        f"{digest(path)}  {path.relative_to(partial)}\n" for path in files
    )
    (partial / "checksums.sha256").write_text(checksums, encoding="utf-8")
    partial.rename(output)
    print(output)


if __name__ == "__main__":
    main()
