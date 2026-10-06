"""Relative input profiles and legacy fixed joint calibration."""

import dataclasses
import hashlib
import json
import math
import pathlib

from ur12e_collection.control import model

RADIANS_PER_COUNT = 2 * math.pi / 4096
MIN_COUNT = -(2**31)
MAX_COUNT = 2**31 - 1


@dataclasses.dataclass(frozen=True)
class GripperReference:
    """An immutable full-open origin with 45-degree relative closing travel."""

    count: int
    closing_sign: int

    def __post_init__(self):
        integer(self.count)
        integer(self.closing_sign)
        if not MIN_COUNT <= self.count <= MAX_COUNT:
            raise ValueError("gripper reference outside encoder range")
        if self.closing_sign not in (-1, 1):
            raise ValueError("gripper closing sign must be -1 or 1")

    def position(self, count: int) -> int:
        """Return a saturated request without wrapping or rebasing counts."""
        integer(count)
        if not MIN_COUNT <= count <= MAX_COUNT:
            raise ValueError("gripper input outside encoder range")
        fraction = self.closing_sign * (count - self.count) / 512
        return round(255 * min(1, max(0, fraction)))


def integer(value):
    """Reject booleans and non-integer encoder/configuration values."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("encoder configuration requires integers")


@dataclasses.dataclass(frozen=True)
class Joint:
    """One explicit signed teaching interval; never a powered goal range."""

    home_count: int | None
    sign: int
    minimum: int
    maximum: int
    ratio: float = 1.0

    def __post_init__(self):
        for value in (self.sign, self.minimum, self.maximum):
            integer(value)
        if (
            self.sign not in (-1, 1)
            or not MIN_COUNT <= self.minimum < self.maximum <= MAX_COUNT
        ):
            raise ValueError("invalid calibrated joint interval/sign")
        if self.home_count is not None:
            self.validate(self.home_count)
        if (
            isinstance(self.ratio, bool)
            or not isinstance(self.ratio, (float, int))
            or not math.isfinite(self.ratio)
            or self.ratio <= 0
        ):
            raise ValueError("ratio must be positive and finite")

    def validate(self, count: int) -> None:
        """Reject another branch rather than wrapping it into the interval."""
        integer(count)
        if not self.minimum <= count <= self.maximum:
            raise ValueError("encoder outside calibrated mechanical interval")

    def relative(self, count: int) -> float:
        """Convert from the optional fixed absolute-calibration origin."""
        if self.home_count is None:
            raise ValueError("absolute mapping requires a fixed leader HOME")
        self.validate(count)
        return (
            (count - self.home_count)
            * self.sign
            * self.ratio
            * RADIANS_PER_COUNT
        )


@dataclasses.dataclass(frozen=True)
class Calibration:
    """Immutable input geometry with optional legacy absolute references."""

    home_rad: tuple | None
    joints: tuple[Joint, ...]
    gripper_open: int | None
    gripper_closed: int | None
    reference: str
    evidence_sha256: str

    def __post_init__(self):
        if self.home_rad is not None:
            model.joints(self.home_rad)
        if (
            not isinstance(self.joints, tuple)
            or len(self.joints) != 6
            or any(not isinstance(joint, Joint) for joint in self.joints)
        ):
            raise ValueError("six calibrated joints are required in ID order")
        if self.home_rad is None:
            if self.gripper_open is not None or self.gripper_closed is not None:
                raise ValueError(
                    "relative input has no fixed gripper endpoints"
                )
            if any(joint.home_count is not None for joint in self.joints):
                raise ValueError("relative input has no fixed leader HOME")
        else:
            if any(joint.home_count is None for joint in self.joints):
                raise ValueError("absolute calibration requires joint HOME")
            for endpoint in (self.gripper_open, self.gripper_closed):
                integer(endpoint)
                if not MIN_COUNT <= endpoint <= MAX_COUNT:
                    raise ValueError("gripper endpoint outside encoder range")
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
        if self.home_rad is None:
            raise ValueError("absolute mapping requires a fixed leader HOME")
        self.validate(raw)
        return tuple(
            home + joint.relative(count)
            for home, joint, count in zip(self.home_rad, self.joints, raw[:6])
        )

    def validate(self, raw: tuple[int, ...]) -> None:
        """Validate all raw inputs without interpreting an absolute posture."""
        if len(raw) != 7:
            raise ValueError("all seven raw encoder values are required")
        for joint, count in zip(self.joints, raw[:6]):
            joint.validate(count)
        integer(raw[6])
        if not MIN_COUNT <= raw[6] <= MAX_COUNT:
            raise ValueError("gripper input outside signed register range")

    def delta(self, raw: tuple, baseline: tuple) -> tuple:
        """Use direct count differences; fixed calibration origins cancel."""
        self.validate(raw)
        self.validate(baseline)
        return tuple(
            (count - start) * joint.sign * joint.ratio * RADIANS_PER_COUNT
            for joint, count, start in zip(self.joints, raw[:6], baseline[:6])
        )

    def gripper(self, raw: int) -> int:
        """Map travel to Robotiq raw position; keep input counts separately."""
        if self.gripper_open is None:
            raise ValueError(
                "absolute gripper mapping requires fixed endpoints"
            )
        integer(raw)
        fraction = (raw - self.gripper_open) / (
            self.gripper_closed - self.gripper_open
        )
        if not MIN_COUNT <= raw <= MAX_COUNT:
            raise ValueError("gripper input outside signed register range")
        return round(255 * min(1, max(0, fraction)))

    def document(self) -> dict:
        """Describe fixed physical context independently of episode mapping."""
        if self.home_rad is None:
            return {
                "schema_version": 4,
                "kind": "leader_relative_input",
                "joints": [
                    {
                        k: v
                        for k, v in dataclasses.asdict(j).items()
                        if k != "home_count"
                    }
                    for j in self.joints
                ],
                "reference": self.reference,
                "evidence_sha256": self.evidence_sha256,
            }
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
    integer(value.get("schema_version"))
    if value.get("schema_version") == 4:
        if (
            set(value)
            != {
                "schema_version",
                "kind",
                "joints",
                "reference",
                "evidence_sha256",
            }
            or value["kind"] != "leader_relative_input"
        ):
            raise ValueError("unexpected relative input fields or kind")
        if any(
            set(j) != {"sign", "minimum", "maximum", "ratio"}
            for j in value["joints"]
        ):
            raise ValueError("unexpected relative joint fields")
        return Calibration(
            None,
            tuple(Joint(None, **j) for j in value["joints"]),
            None,
            None,
            value["reference"],
            value["evidence_sha256"],
        )
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


def validate_binding(config):
    """Reject stale assembly, changed HOME or altered embedded calibration."""
    leader = config["gello"]
    value = leader.get("calibration")
    if value is None:
        return
    if set(value) != {
        "schema_version",
        "setup_id",
        "simulated",
        "calibration_id",
        "document",
        "physical_verified",
    }:
        raise ValueError("leader calibration binding fields differ")
    if value["schema_version"] != 1 or value["physical_verified"] is not False:
        raise ValueError("physical calibration acceptance is not implemented")
    setup = leader.get("setup")
    if setup != {"id": value["setup_id"], "simulated": value["simulated"]}:
        raise ValueError("leader assembly differs from active calibration")
    calibrated = from_document(value["document"])
    if calibrated.identity() != value["calibration_id"]:
        raise ValueError("leader calibration identity differs")
    if (
        calibrated.home_rad is not None
        and list(calibrated.home_rad) != config["ur"]["ready_q_rad"]
    ):
        raise ValueError("leader calibration and follower HOME differ")
