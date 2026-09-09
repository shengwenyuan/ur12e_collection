"""Explicit offline-only provenance and small synthetic camera fixtures."""

import dataclasses

import numpy as np
import pytest

from ur12e_collection import codecs, contracts, matching

EPOCH = 1_700_000_000_000_000_000


@pytest.fixture
def frame_factory():
    """Construct source timestamps separately from host monotonic receipt."""

    def make(
        role, time_ns, index=0, *, depth_index=None, receipt=None, generation=0
    ):
        stamp = contracts.SampleTime(
            EPOCH + time_ns,
            "fixture-camera",
            time_ns if receipt is None else receipt,
        )
        return matching.Frame(
            role,
            generation,
            "fixture-unix",
            EPOCH + time_ns,
            contracts.Provenance(role, index, stamp, True),
            contracts.Provenance(
                role, index if depth_index is None else depth_index, stamp, True
            ),
            EPOCH + time_ns,
        )

    return make


@pytest.fixture
def snapshot():
    """A visibly synthetic station, with no real identities or calibration."""
    return {
        "task": "synthetic-test",
        "software_revision": "test-fixture",
        "clock_epoch": "unix",
        "clock_id": "fixture-unix",
        "calibration": None,
        "cameras": {
            role: {
                "source_id": role,
                "depth_scale_m": 0.000123,
                "color_intrinsics": {
                    "width": 640,
                    "height": 480,
                    "fx": 400,
                    "fy": 400,
                    "ppx": 320,
                    "ppy": 240,
                },
            }
            for role in contracts.CAMERA_ROLES
        },
    }


@pytest.fixture
def group_factory(frame_factory):
    """Make spatially varying RGB and depth, including uint16 edge values."""

    def make(index=0):
        time_ns = 1_000_000 + index * 33_333_333
        members = []
        for offset, role in enumerate(contracts.CAMERA_ROLES):
            rgb = np.zeros((480, 640, 3), np.uint8)
            rgb[:, :, offset] = 180
            rgb[100:180, 40 + index : 120 + index] = [220, 80, 30]
            depth = (
                np.arange(480 * 640, dtype=np.uint32).reshape(480, 640) % 65536
            ).astype(np.uint16)
            frame = frame_factory(role, time_ns, index)
            members.append(
                dataclasses.replace(frame, payload=codecs.Images(rgb, depth))
            )
        return matching.Match(
            members[0], tuple(members), "accepted", time_ns + 1
        )

    return make
