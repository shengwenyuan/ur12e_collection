"""Fixed joint calibration, independent of each episode mapping reference."""

import dataclasses
import hashlib
import json
import math
import pathlib

from ur12e_collection.control import model

RADIANS_PER_COUNT = 2 * math.pi / 4096
MIN_COUNT = -(2**31)
MAX_COUNT = 2**31 - 1


def integer(value):
    """Reject booleans and non-integer encoder/configuration values."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("encoder configuration requires integers")


@dataclasses.dataclass(frozen=True)
class Joint:
    """One explicit signed teaching interval; never a powered goal range."""

    home_count: int
    sign: int
    minimum: int
    maximum: int
    ratio: float = 1.0

    def __post_init__(self):
        for value in (self.home_count, self.sign, self.minimum, self.maximum):
            integer(value)
        if (
            self.sign not in (-1, 1)
            or not MIN_COUNT <= self.minimum < self.maximum <= MAX_COUNT
            or not self.minimum <= self.home_count <= self.maximum
        ):
            raise ValueError("invalid calibrated joint interval/sign")
        if (
            isinstance(self.ratio, bool)
            or not isinstance(self.ratio, (float, int))
            or not math.isfinite(self.ratio)
            or self.ratio <= 0
        ):
            raise ValueError("ratio must be positive and finite")

    def relative(self, count: int) -> float:
        """Reject another branch rather than wrapping it into the interval."""
        integer(count)
        if not self.minimum <= count <= self.maximum:
            raise ValueError("encoder outside calibrated mechanical interval")
        return (
            (count - self.home_count)
            * self.sign
            * self.ratio
            * RADIANS_PER_COUNT
        )


@dataclasses.dataclass(frozen=True)
class Calibration:
    """One immutable physical reference; all six directions must be verified."""

    home_rad: tuple
    joints: tuple[Joint, ...]
    gripper_open: int
    gripper_closed: int
    reference: str
    evidence_sha256: str

    def __post_init__(self):
        model.joints(self.home_rad)
        if (
            not isinstance(self.joints, tuple)
            or len(self.joints) != 6
            or any(not isinstance(joint, Joint) for joint in self.joints)
        ):
            raise ValueError("six calibrated joints are required in ID order")
        for endpoint in (self.gripper_open, self.gripper_closed):
            integer(endpoint)
            if not MIN_COUNT <= endpoint <= MAX_COUNT:
                raise ValueError(
                    "gripper endpoint outside signed register range"
                )
        if not 20 <= abs(self.gripper_closed - self.gripper_open) < 2048:
            raise ValueError("invalid gripper travel")
        if (
            not isinstance(self.reference, str)
            or not self.reference.strip()
            or not isinstance(self.evidence_sha256, str)
            or len(self.evidence_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.evidence_sha256)
        ):
            raise ValueError(
                "reference description and evidence SHA256 required"
            )

    def angles(self, raw: tuple[int, ...]) -> tuple:
        """Convert measured counts into the fixed follower coordinate frame."""
        if len(raw) != 7:
            raise ValueError("all seven raw encoder values are required")
        return tuple(
            home + joint.relative(count)
            for home, joint, count in zip(self.home_rad, self.joints, raw[:6])
        )

    def gripper(self, raw: int) -> int:
        """Map travel to Robotiq raw position; keep input counts separately."""
        integer(raw)
        fraction = (raw - self.gripper_open) / (
            self.gripper_closed - self.gripper_open
        )
        if not MIN_COUNT <= raw <= MAX_COUNT:
            raise ValueError("gripper input outside signed register range")
        return round(255 * min(1, max(0, fraction)))

    def document(self) -> dict:
        """Describe fixed physical context independently of episode mapping."""
        return {
            "schema_version": 3,
            "kind": "leader_joint_calibration",
            **dataclasses.asdict(self),
        }

    def identity(self) -> str:
        """Hash calibration fields, including the source evidence identity."""
        return hashlib.sha256(
            json.dumps(
                self.document(), sort_keys=True, allow_nan=False
            ).encode()
        ).hexdigest()

    def save(self, path: pathlib.Path) -> None:
        """Create a new versioned calibration file, never overwrite another."""
        value = self.document()
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2) + "\n")


def load(path: pathlib.Path) -> Calibration:
    """Strict fields prevent ignored session offsets from entering a config."""
    return from_document(json.loads(path.read_text(encoding="utf-8")))


def from_document(document: dict) -> Calibration:
    """Validate a detached embedded calibration with the same file contract."""
    value = json.loads(json.dumps(document, allow_nan=False))
    if not isinstance(value, dict):
        raise ValueError("calibration must be a JSON object")
    fields = {field.name for field in dataclasses.fields(Calibration)}
    if set(value) != fields | {"schema_version", "kind"}:
        raise ValueError("unexpected or missing calibration fields")
    version = value.pop("schema_version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != 3
        or value.pop("kind") != "leader_joint_calibration"
    ):
        raise ValueError("unsupported calibration version or kind")
    value["home_rad"] = tuple(value["home_rad"])
    value["joints"] = tuple(Joint(**item) for item in value["joints"])
    return Calibration(**value)


def reference(path: pathlib.Path) -> dict:
    """Summarize stability without attesting a physical pose or direction."""
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    if (
        len(rows) < 30
        or rows[-1]["start_ns"] - rows[0]["start_ns"] < 1_000_000_000
    ):
        raise ValueError("reference needs >=30 unique samples over >=1 second")
    epochs = {row.get("epoch") for row in rows}
    if len(epochs) != 1:
        raise ValueError("reference spans different source epochs")
    for index, row in enumerate(rows):
        for key in ("sequence", "start_ns", "end_ns"):
            integer(row[key])
            if row[key] < 0:
                raise ValueError("negative reference sequence or time")
        if (
            row["sequence"] != index
            or len(row["errors"]) != 7
            or any(row["errors"])
            or len(row["position"]) != 7
        ):
            raise ValueError("reference contains invalid or incomplete samples")
        if row["end_ns"] < row["start_ns"]:
            raise ValueError("reference acquisition time runs backward")
        if (
            index
            and not 0
            < row["start_ns"] - rows[index - 1]["start_ns"]
            <= 100_000_000
        ):
            raise ValueError(
                "reference samples are repeated, reversed or stale"
            )
        for count in row["position"]:
            integer(count)
            if not MIN_COUNT <= count <= MAX_COUNT:
                raise ValueError("reference outside signed register range")
    values = list(zip(*(row["position"] for row in rows)))
    spreads = [max(v) - min(v) for v in values]
    if max(spreads) > 2:
        raise ValueError("reference moves more than two encoder counts")
    return {
        "home_counts": list(rows[-1]["position"]),
        "reference_sample": rows[-1],
        "reference_selection": "last_actual_sample_in_stable_capture",
        "spread_counts": spreads,
        "samples": len(rows),
        "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "physical_reference_confirmed": False,
        "directions_confirmed": False,
        "motion_ready": False,
    }
