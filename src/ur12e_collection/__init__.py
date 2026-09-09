"""Collection foundations; importing this package opens no devices."""

from importlib import metadata


def version() -> str:
    """Return the installed distribution version."""
    return metadata.version("ur12e-collection")
