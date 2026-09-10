"""Durability primitives for local recording and offline delivery."""

import os
import pathlib


def sync(path: pathlib.Path) -> None:
    """Flush a closed file or directory before publishing a local artifact."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish(partial: pathlib.Path, destination: pathlib.Path) -> None:
    """Flush an owned staging tree and publish without replacing a result."""
    for path in sorted(
        partial.rglob("*"), key=lambda p: len(p.parts), reverse=True
    ):
        sync(path)
    sync(partial)
    if destination.exists():
        raise FileExistsError(destination)
    partial.rename(destination)
    try:
        sync(destination.parent)
    except OSError:
        destination.rename(partial)
        raise
