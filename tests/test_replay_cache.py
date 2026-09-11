"""Disposable replay must reject missing/corrupted source payloads."""

import importlib.util
import io
import json
import pathlib
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from ur12e_collection import codecs, contracts

SPEC = importlib.util.spec_from_file_location(
    "lab_cache", pathlib.Path(__file__).parent / "replay" / "cache.py"
)
CACHE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHE)


def payloads():
    depth = (
        np.arange(480 * 640, dtype=np.uint32)
        .reshape(480, 640)
        .astype(np.uint16)
    )
    context = {
        "members": [{"role": role} for role in contracts.CAMERA_ROLES],
        "depth_sha256": {
            role: codecs.depth_digest(depth) for role in contracts.CAMERA_ROLES
        },
    }
    messages = [("camera/frame_set", SimpleNamespace(data=json.dumps(context)))]
    for role in contracts.CAMERA_ROLES:
        rgb = codecs.VideoEncoder().encode(
            np.zeros((480, 640, 3), np.uint8), 1_000_000_000
        )
        messages.extend(
            [
                (f"camera/{role}/rgb", SimpleNamespace(data=rgb)),
                (
                    f"camera/{role}/depth",
                    SimpleNamespace(data=codecs.encode_depth(depth)),
                ),
            ]
        )
    return depth, messages


def test_cache_preserves_depth_and_rejects_missing_images():
    depth, messages = payloads()
    streams = {
        (role, kind): io.BytesIO()
        for role in contracts.CAMERA_ROLES
        for kind in ("rgb", "depth")
    }
    with mock.patch.object(
        CACHE.projection, "messages", return_value=iter(messages)
    ):
        assert len(CACHE._decode(None, streams)) == 1
    for role in contracts.CAMERA_ROLES:
        assert (
            streams[role, "depth"].getvalue() == depth.astype("<u2").tobytes()
        )
        assert len(streams[role, "rgb"].getvalue()) == 480 * 640 * 3
    with mock.patch.object(
        CACHE.projection, "messages", return_value=iter(messages[:-1])
    ):
        with pytest.raises(ValueError, match="incomplete"):
            CACHE._decode(None, streams)


def test_cache_rejects_corrupted_depth_and_partial_input(tmp_path):
    _, messages = payloads()
    context = json.loads(messages[0][1].data)
    context["depth_sha256"]["wrist"] = "0" * 64
    messages[0] = (messages[0][0], SimpleNamespace(data=json.dumps(context)))
    streams = {
        (role, kind): io.BytesIO()
        for role in contracts.CAMERA_ROLES
        for kind in ("rgb", "depth")
    }
    with mock.patch.object(
        CACHE.projection, "messages", return_value=iter(messages)
    ):
        with pytest.raises(ValueError, match="hash mismatch"):
            CACHE._decode(None, streams)
    (tmp_path / "metadata.json").write_text(json.dumps({"state": "partial"}))
    with pytest.raises(ValueError, match="complete episodes"):
        CACHE.build(tmp_path, tmp_path / "out")
    assert not (tmp_path / "out").exists()
