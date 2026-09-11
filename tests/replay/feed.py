"""Disposable paced lab-image input; never opens hardware or control sockets."""

import hashlib
import json
import pathlib

import numpy as np

from ur12e_collection import codecs, contracts, matching, snapshots, synthetic


class Cache:
    """Memory-map raw images, preserving immutable original group evidence."""

    def __init__(self, path: pathlib.Path):
        raw = (path / "manifest.json").read_bytes()
        self.identity = hashlib.sha256(raw).hexdigest()
        self.manifest = json.loads(raw)
        self.groups = self.manifest["groups"]
        if (
            self.manifest["schema_version"] != 1
            or self.manifest["origin"] != "replay"
            or not self.groups
            or self.manifest["frames_per_role"] != len(self.groups)
        ):
            raise ValueError("unsupported replay cache")
        self.arrays = {}
        for role in contracts.CAMERA_ROLES:
            for kind, shape, dtype in (
                ("rgb", (480, 640, 3), np.uint8),
                ("depth", (480, 640), np.dtype("<u2")),
            ):
                file = path / f"{role}.{kind}.raw"
                expected = (
                    len(self.groups)
                    * int(np.prod(shape))
                    * np.dtype(dtype).itemsize
                )
                if file.stat().st_size != expected:
                    raise ValueError("replay cache size differs from manifest")
                self.arrays[role, kind] = np.memmap(
                    file,
                    dtype=dtype,
                    mode="r",
                    shape=(len(self.groups), *shape),
                )
        members = [m for g in self.groups for m in g["members"]]
        self.receipt_origin = min(
            m["color"]["time"]["received_monotonic_ns"] for m in members
        )
        self.source_origin = min(m["timestamp_ns"] for m in members)
        self.period_ns = (
            max(
                max(
                    m["color"]["time"]["received_monotonic_ns"] for m in members
                )
                - self.receipt_origin,
                max(m["timestamp_ns"] for m in members) - self.source_origin,
            )
            + 33_333_333
        )
        self.sequence_stride = 1 + max(
            m[kind]["sequence"] for m in members for kind in ("color", "depth")
        )

    def member(self, role, index):
        """Resolve by role rather than assuming a metadata array order."""
        return next(
            m for m in self.groups[index]["members"] if m["role"] == role
        )

    def due(self, role, sequence):
        """Original relative receipt timing, with an explicit replay cycle."""
        cycle, index = divmod(sequence, len(self.groups))
        original = self.member(role, index)["color"]["time"][
            "received_monotonic_ns"
        ]
        return cycle * self.period_ns + original - self.receipt_origin

    def frame(self, role, sequence, clock_id, receipt_ns, unix_origin):
        """Copy bounded payloads; original time remains in replay provenance."""
        cycle, index = divmod(sequence, len(self.groups))
        member = self.member(role, index)
        image = codecs.Images(
            *(
                self.arrays[role, kind][index].copy()
                for kind in ("rgb", "depth")
            )
        )
        if (
            codecs.depth_digest(image.depth)
            != self.groups[index]["depth_sha256"][role]
        ):
            raise ValueError("cached depth hash mismatch")
        provenance = {}
        for kind in ("color", "depth"):
            original = member[kind]
            provenance[kind] = contracts.Provenance(
                f"replay-{original['source_id']}",
                cycle * self.sequence_stride + original["sequence"],
                contracts.SampleTime(
                    original["time"]["source_ns"],
                    f"replay-original:{original['time']['source_clock']}",
                    receipt_ns,
                ),
                True,
            )
        offset = unix_origin - self.source_origin + cycle * self.period_ns
        return matching.Frame(
            role,
            0,
            clock_id,
            member["timestamp_ns"] + offset,
            provenance["color"],
            provenance["depth"],
            member["depth_timestamp_ns"] + offset,
            image,
        )

    def snapshot(self, epoch, revision):
        """Use replay identities; never activate historical robot addresses."""
        config = synthetic.configuration()
        config["station_id"] = "lab-image-replay"
        observed = json.loads(
            json.dumps(self.manifest["source_metadata"]["snapshot"]["cameras"])
        )
        for role, camera in observed.items():
            camera["source_id"] = "replay-" + camera["source_id"]
            camera["usb"] = "replay-no-usb"
            if "firmware" in camera:
                camera["firmware"] = "recorded:" + camera["firmware"]
            config["cameras"][role] = {
                "serial": camera["source_id"],
                "model": camera["model"],
            }
        return snapshots.build(
            config,
            observed,
            {
                "task": f"lab-image-replay cache-sha256:{self.identity}",
                "software_revision": revision,
                "clock_epoch": "unix",
                "clock_id": f"replay:{epoch}",
                "clock_basis": "synthetic",
                "clock_validated": False,
                "simulated": True,
            },
        )

    def close(self):
        """Release mappings after all owned image copies have been submitted."""
        for array in self.arrays.values():
            array._mmap.close()  # pylint: disable=protected-access
        self.arrays.clear()
