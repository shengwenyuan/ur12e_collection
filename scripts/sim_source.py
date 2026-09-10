"""Freeze source overlays so one simulator run cannot observe later edits."""

import hashlib
import json
import pathlib
import shutil
import subprocess


def freeze(root: pathlib.Path, destination: pathlib.Path) -> dict:
    """Copy only runtime/check sources and record their exact content hashes."""
    for source, target in (("src", "src"), ("tests/simulation", "checks")):
        shutil.copytree(
            root / source,
            destination / target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    hashes = {}
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(destination))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    fingerprint = hashlib.sha256(
        json.dumps(hashes, sort_keys=True).encode()
    ).hexdigest()
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    return {
        "source_revision": f"{revision[:12]}-source-{fingerprint[:12]}",
        "git_revision": revision,
        "source_files_sha256": hashes,
    }
