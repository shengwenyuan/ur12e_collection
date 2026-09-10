"""Effective camera profile, shared by configuration, runtime and snapshots."""

WAIT_NS = 75_000_000
EMPTY_POLL_NS = 1_000_000


def resolve(config: dict) -> dict:
    """Expand legacy station documents without mutating their stored values."""
    return {
        "wait_ns": WAIT_NS,
        "empty_poll_ns": EMPTY_POLL_NS,
        **config.get("capture", {}),
        "depth_verification": "final_file_pixel_hash",
    }
