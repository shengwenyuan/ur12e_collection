"""Serial-bound external extrinsics retain source evidence without refitting."""

import json

from ur12e_collection import station
from ur12e_collection.calibration import manifest


def activate(source_path, station_path, serial):
    """Import one fixed-camera report atomically, resolving role by serial."""
    # YAML is an import dependency, never a recording-loop dependency.
    # pylint: disable=import-outside-toplevel
    import yaml

    text = source_path.read_bytes().decode("utf-8")
    header = manifest.HEADER.search(text)
    if header is None or header.group(2) != serial:
        raise ValueError("requested serial differs from external YAML header")
    report = yaml.safe_load(text)
    transform = manifest.external_report(report)
    json.dumps(report, allow_nan=False)
    digest = manifest.source_hash(text)

    def change(config):
        manifest.identity(config["ur"]["serial"])
        roles = [
            role
            for role, camera in config["cameras"].items()
            if camera["serial"] == serial
        ]
        if len(roles) != 1 or roles[0] == "wrist":
            raise ValueError(
                "external serial must match one fixed station camera"
            )
        role = roles[0]
        declared = config.setdefault(
            "setup",
            {
                "base_id": "ur-" + str(config["ur"]["serial"]),
                "mounts": {
                    r: "unspecified-" + str(c["serial"])
                    for r, c in config["cameras"].items()
                },
                "simulated": False,
            },
        )
        declared["mounts"][role] = serial + "-" + digest[:16]
        result = {
            "schema_version": 4,
            "context": {
                "role": role,
                "camera_serial": serial,
                "base_id": declared["base_id"],
                "mount_id": declared["mounts"][role],
                "simulated": False,
            },
            "solution": {"round": "fixed", "T_base_camera": transform},
            "source": {
                "name": source_path.name,
                "camera_name": header.group(1),
                "sha256": digest,
                "yaml": text,
                "report": report,
            },
            "validation": {
                "status": "external_provided",
                "collector_validation": "not_run",
            },
        }
        result["calibration_id"] = manifest.digest(result)
        selected = config["calibration"] or {"schema_version": 1, "cameras": {}}
        selected["cameras"][role] = result
        config["calibration"] = selected
        return config

    return station.update(station_path, change)
