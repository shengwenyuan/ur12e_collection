"""Task descriptions mapped to portable, unique collection directories."""

import json
import pathlib
import re


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate task description: {key}")
        result[key] = value
    return result


def load(path: pathlib.Path) -> dict[str, str]:
    """Validate the complete route table before any hardware is opened."""
    routes = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique
    )
    if not isinstance(routes, dict) or not routes:
        raise ValueError("task routes must be a nonempty JSON object")
    names = set()
    for description, directory in routes.items():
        if not description.strip():
            raise ValueError("task description must not be empty")
        if not isinstance(directory, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", directory
        ):
            raise ValueError(f"invalid task directory: {directory!r}")
        # Also prevent aliases on case-insensitive Mac filesystems.
        if directory.casefold() in names:
            raise ValueError(f"duplicate task directory: {directory}")
        names.add(directory.casefold())
    return routes
