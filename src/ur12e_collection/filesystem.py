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
