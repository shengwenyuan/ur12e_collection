"""Pinned local URDF FK; no controller RPC, IK or simulation dependency."""

import hashlib
import xml.etree.ElementTree as ET
import numpy as np

from ur12e_collection import contracts
from ur12e_collection.control import model


def vector(values, size):
    """Validate finite numeric coordinates without changing their frame."""
    result = np.asarray(values, dtype=float)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError("invalid kinematic vector")
    return result


JOINTS = contracts.JOINT_NAMES


def rotation(axis, angle):
    """Rodrigues rotation in homogeneous column-vector convention."""
    x, y, z = axis
    cosine, sine = np.cos(angle), np.sin(angle)
    delta = 1 - cosine
    result = np.eye(4)
    result[:3, :3] = [
        [
            cosine + x * x * delta,
            x * y * delta - z * sine,
            x * z * delta + y * sine,
        ],
        [
            y * x * delta + z * sine,
            cosine + y * y * delta,
            y * z * delta - x * sine,
        ],
        [
            z * x * delta - y * sine,
            z * y * delta + x * sine,
            cosine + z * z * delta,
        ],
    ]
    return result


class Kinematics:
    """Preload only the root-to-flange six-joint chain once at startup."""

    def __init__(self, source: bytes, sha256: str):
        self.source = source
        self.sha256 = sha256
        if hashlib.sha256(source).hexdigest() != sha256:
            raise ValueError("FK asset SHA256 mismatch")
        robot = ET.fromstring(source)
        joints = {
            joint.find("child").get("link"): joint
            for joint in robot.findall("joint")
        }
        chain, visited = [], set()
        link = "flange"
        while link in joints:
            if link in visited:
                raise ValueError("cyclic FK chain")
            visited.add(link)
            joint = joints[link]
            chain.append(joint)
            link = joint.find("parent").get("link")
        if not chain:
            raise ValueError("FK asset has no flange chain")
        self.chain = []
        indices = []
        for joint in reversed(chain):
            fixed, axis, index = _segment(joint)
            if index is not None:
                indices.append(index)
            self.chain.append((fixed, axis, index))
        if indices != list(range(6)):
            raise ValueError("FK chain must contain the six ordered UR joints")

    def position(self, q) -> np.ndarray:
        """Return nominal root-frame reference position in meters."""
        model.joints(q)
        q = vector(q, 6)
        transform = np.eye(4)
        for fixed, axis, index in self.chain:
            transform = transform @ fixed
            if index is not None:
                transform = transform @ rotation(axis, q[index])
        return transform[:3, 3]


def _triple(node, name, default):
    value = default if node is None else node.get(name, default)
    return vector([float(part) for part in value.split()], 3)


def _origin(node):
    xyz = _triple(node, "xyz", "0 0 0")
    rpy = _triple(node, "rpy", "0 0 0")
    result = (
        rotation((0, 0, 1), rpy[2])
        @ rotation((0, 1, 0), rpy[1])
        @ rotation((1, 0, 0), rpy[0])
    )
    result[:3, 3] = xyz
    return result


def _segment(joint):
    kind = joint.get("type")
    index = None
    axis = _triple(joint.find("axis"), "xyz", "1 0 0")
    if kind in ("revolute", "continuous"):
        index = JOINTS.index(joint.get("name"))
        length = np.linalg.norm(axis)
        if length == 0:
            raise ValueError("FK joint has zero axis")
        axis = axis / length
    elif kind != "fixed":
        raise ValueError("FK chain must contain fixed/revolute joints")
    return _origin(joint.find("origin")), axis, index
