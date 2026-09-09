"""Independent episode H.264 encoders and exact aligned-depth PNG payloads."""

import dataclasses
import fractions
import hashlib
import math

import av
import cv2
import numpy as np

from ur12e_collection import matching


@dataclasses.dataclass(frozen=True)
class Images:
    """Owned RGB8 and aligned raw Z16 arrays; callers transfer ownership."""

    rgb: np.ndarray
    depth: np.ndarray

    def validate(self) -> None:
        """Reject incompatible shape or dtype without silent conversion."""
        if self.rgb.shape != (480, 640, 3) or self.rgb.dtype != np.uint8:
            raise ValueError("RGB must be 640x480 RGB8")
        if self.depth.shape != (480, 640) or self.depth.dtype != np.uint16:
            raise ValueError("depth must be aligned 640x480 uint16")


def depth_digest(depth: np.ndarray) -> str:
    """Hash a portable little-endian representation of the unmodified depth."""
    return hashlib.sha256(depth.astype("<u2", copy=False).tobytes()).hexdigest()


def encode_depth(depth: np.ndarray) -> bytes:
    """Encode and verify every raw depth value, including zeros and 65535."""
    if depth.shape != (480, 640) or depth.dtype != np.uint16:
        raise ValueError("depth must be aligned 640x480 uint16")
    ok, encoded = cv2.imencode(".png", depth, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    if not ok or not np.array_equal(depth, decode_depth(encoded.tobytes())):
        raise RuntimeError("depth PNG did not preserve every pixel")
    return encoded.tobytes()


def decode_depth(data: bytes) -> np.ndarray:
    """Decode native uint16 without filtering, clipping or normalization."""
    result = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if (
        result is None
        or result.dtype != np.uint16
        or result.shape != (480, 640)
    ):
        raise ValueError("invalid aligned uint16 depth PNG")
    return result


def nal_types(data: bytes) -> set[int]:
    """Inspect Annex B boundaries; do not accept length-prefixed AVC packets."""
    return {part[0] & 31 for part in data.split(b"\x00\x00\x01")[1:] if part}


class VideoEncoder:
    """Fresh, zero-delay H.264 stream for exactly one camera in one episode."""

    def __init__(self, crf: int = 20):
        if (
            not isinstance(crf, int) or isinstance(crf, bool)
        ) or not 0 <= crf <= 51:
            raise ValueError("CRF must be an integer from 0 to 51")
        self._encoder = av.CodecContext.create("libx264", "w")
        self._encoder.width, self._encoder.height = 640, 480
        self._encoder.pix_fmt = "yuv420p"
        self._encoder.time_base = fractions.Fraction(
            matching.RGB_TIME_QUANTUM_NS, 1_000_000_000
        )
        self._encoder.framerate = fractions.Fraction(30, 1)
        self._encoder.gop_size = 30
        self._encoder.max_b_frames = 0
        self._encoder.thread_count = 1
        self._encoder.options = {
            "crf": str(crf),
            "preset": "veryfast",
            "tune": "zerolatency",
            "x264-params": "repeat-headers=1:annexb=1:scenecut=0:bframes=0",
        }
        self._origin: int | None = None
        self._previous = -1

    def encode(self, rgb: np.ndarray, timestamp_ns: int) -> bytes:
        """Encode one acquisition, rejecting timing collisions."""
        if rgb.shape != (480, 640, 3) or rgb.dtype != np.uint8:
            raise ValueError("RGB must be 640x480 RGB8")
        if (
            not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool)
        ) or timestamp_ns < 0:
            raise ValueError(
                "acquisition timestamp must be nonnegative integer ns"
            )
        if self._origin is None:
            self._origin = timestamp_ns
        pts = (timestamp_ns - self._origin) // matching.RGB_TIME_QUANTUM_NS
        if pts <= self._previous:
            raise ValueError("video PTS collision or backwards timestamp")
        frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
        frame.pts, frame.time_base = pts, self._encoder.time_base
        packets = self._encoder.encode(frame)
        if len(packets) != 1 or packets[0].pts != pts or packets[0].dts != pts:
            raise RuntimeError("encoder violated one-frame zero-delay contract")
        data = bytes(packets[0])
        types = nal_types(data)
        if not types or (packets[0].is_keyframe and not {5, 7, 8} <= types):
            raise RuntimeError("H.264 keyframe lacks Annex B IDR/SPS/PPS")
        self._previous = pts
        return data

    def finish(self) -> None:
        """Require zero-delay encoding with no pending packets."""
        if self._encoder.encode(None):
            raise RuntimeError("unexpected delayed H.264 packets")


def rgb_psnr(reference: np.ndarray, decoded: np.ndarray) -> float | None:
    """Measure RGB loss; None denotes an exact match."""
    error = float(np.mean((reference.astype(np.float32) - decoded) ** 2))
    return 10 * math.log10(255**2 / error) if error else None
