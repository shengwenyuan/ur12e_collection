"""Convert measured colleague waypoints without importing solver assumptions."""

from ur12e_collection.calibration import aprilgrid, routes

ROLES = {
    "wrist": "camera_1",
    "third_left": "camera_2",
    "third_right": "camera_3",
}


def convert(source, context, limits):
    """Keep actual radians/order; freeze held-out membership before replay."""
    role = context["role"]
    if (
        source["camera_name"] != ROLES[role]
        or source["camera_serial"] != context["camera_serial"]
    ):
        raise ValueError("colleague source differs from selected camera")
    entries = source["waypoints"]
    if source["count"] != len(entries):
        raise ValueError("source waypoint count differs")
    if [p["number"] for p in entries] != list(range(1, len(entries) + 1)):
        raise ValueError("source waypoint numbering is not ordered")
    if len(entries) < 30:
        raise ValueError("this import requires at least 30 measured waypoints")
    document = dict(context)
    document.update(
        schema_version=1,
        joint_names=routes.JOINT_NAMES,
        units="rad",
        board_attachment="base" if role == "wrist" else "flange",
        start_q=entries[0]["actual_joints_rad"],
        profile={"width": 640, "height": 480, "fps": 30, "format": "rgb8"},
        waypoints=[
            {
                "pose_id": entry["name"],
                "q": entry["actual_joints_rad"],
                "split": (
                    "validation" if entry["number"] % 6 == 0 else "training"
                ),
            }
            for entry in entries
        ],
    )
    aprilgrid.Grid(**document["board"])
    routes.parse(document, role, limits)
    return document
