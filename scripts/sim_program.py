"""Prepare a native Home fixture from the installed, verified URSim program."""

import gzip
import hashlib
import math
import subprocess
import xml.etree.ElementTree as ET

HOME = (0.0, -math.pi / 2, -math.pi / 2, -math.pi / 2, math.pi / 2, 0.0)
PROGRAM = "/ursim/programs/collector_ready.urp"


def prepare(container: str) -> dict:
    """Clone the one-node probe at native defaults; never edit installation."""

    def read(path):
        return subprocess.check_output(
            ["docker", "exec", container, "cat", path]
        )

    installation = read("/ursim/programs/default.installation")
    settings = ET.fromstring(gzip.decompress(installation))
    home = settings.find("SafeHomeSettings")
    if home is None or home.get("enabled") != "true":
        raise ValueError("simulator installation Home is not configured")
    q = tuple(float(v) for v in home.get("position", "").split(","))
    if len(q) != 6 or any(not math.isfinite(v) for v in q):
        raise ValueError("invalid native Home joint vector")
    if max(abs(a - b) for a, b in zip(q, HOME)) > 1e-6:
        raise ValueError("installation Home differs from configured READY")
    program = ET.fromstring(gzip.decompress(read("/ursim/programs/ready.urp")))
    main = program.find("children/MainProgram")
    if (
        program.tag != "URProgram"
        or program.get("installation") != "default"
        or main is None
        or main.get("runOnlyOnce") != "true"
    ):
        raise ValueError("native Home probe structure differs")
    children = list(main.find("children"))
    if len(children) != 1 or children[0].tag != "SafeHome":
        raise ValueError("native Home must contain exactly one Home node")
    speed, acceleration = math.radians(60), math.radians(80)
    children[0].set("speed", repr(speed))
    children[0].set("acceleration", repr(acceleration))
    children[0].set("positionOptionType", "SPEED_AND_ACCELERATION")
    program.find("children").insert(1, _current_pose_start())
    program.set("name", "collector_ready")
    content = gzip.compress(ET.tostring(program), mtime=0)
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "python3",
            "-c",
            "import pathlib,sys; "
            "pathlib.Path('/ursim/programs/collector_ready.urp')"
            ".write_bytes(sys.stdin.buffer.read())",
        ],
        input=content,
        check=True,
    )
    return {
        "program": PROGRAM,
        "q": q,
        "speed_rad_s": speed,
        "acceleration_rad_s2": acceleration,
        "program_sha256": hashlib.sha256(content).hexdigest(),
        "installation_sha256": hashlib.sha256(installation).hexdigest(),
    }


def _current_pose_start():
    """Use UR's documented first variable-waypoint pattern."""
    # UR's documented variable-current-pose start avoids a pendant AutoMove.
    # It is a zero-displacement preamble, not a second HOME motion or waypoint.
    before = ET.Element("SpecialSequence", {"type": "BeforeStart"})
    sequence = ET.SubElement(before, "children")
    assignment = ET.SubElement(
        sequence, "Assignment", {"valueSource": "Expression"}
    )
    variable = ET.SubElement(
        assignment,
        "variable",
        {"name": "collector_start", "prefersPersistentValue": "false"},
    )
    ET.SubElement(variable, "initializeExpression")
    expression = ET.SubElement(assignment, "expression")
    for char in "get_actual_tcp_pose()":
        ET.SubElement(expression, "ExpressionChar", {"character": char})
    move = ET.SubElement(
        sequence,
        "Move",
        {
            "motionType": "MoveL",
            "speed": "0.25",
            "acceleration": "1.2",
            "recalculateMotions": "false",
        },
    )
    ET.SubElement(
        move,
        "feature",
        {"class": "GeomFeatureReference", "referencedName": "Joint_0_name"},
    )
    waypoint = ET.SubElement(
        ET.SubElement(move, "children"),
        "Waypoint",
        {
            "type": "Variable",
            "name": "Current_position",
            "kinematicsFlags": "-1",
        },
    )
    ET.SubElement(waypoint, "motionParameters")
    ET.SubElement(
        waypoint, "variable", {"reference": "../../../../Assignment/variable"}
    )
    return before
