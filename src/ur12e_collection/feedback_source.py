"""Read-only device workers; output subscriptions and GET requests only."""

import time

from ur12e_collection import contracts, hande, ur

UR_OUTPUTS = [
    "timestamp",
    "actual_q",
    "actual_qd",
    "actual_current",
    "actual_TCP_pose",
    "robot_mode",
    "safety_mode",
]


def _provenance(identity, index, source_ns, simulated=False):
    return contracts.Provenance(
        identity,
        index,
        contracts.SampleTime(
            source_ns,
            "unavailable" if source_ns is None else "ur_controller_uptime",
            time.monotonic_ns(),
        ),
        simulated,
    )


def ur_stream(config, stop):
    """Observe identity and controller outputs without a control connection."""
    host = config["host"]
    identity = ur.dashboard(host)
    responses = identity["responses"]
    if (
        identity["state"] != "available"
        or responses.get("get serial number") != config["serial"]
    ):
        raise ValueError("UR identity readback differs from configured serial")
    import rtde_receive  # pylint: disable=import-outside-toplevel,import-error

    receiver = rtde_receive.RTDEReceiveInterface(host, 125.0, UR_OUTPUTS)
    try:
        yield {
            "source_id": config["serial"],
            "dashboard": identity,
            "endpoint": host,
            "transport": "rtde_outputs",
            "tcp_reference": "base_to_active_tcp",
            "tcp_offset": "controller_active_value_not_read_back",
            "coherence": "timestamp_bracket_not_atomic_packet",
        }
        index = 0
        while not stop.is_set():
            if not receiver.isConnected():
                raise ConnectionError("UR feedback disconnected")
            sample = ur.coherent_sample(receiver)
            provenance = _provenance(
                config["serial"],
                index,
                round(sample["controller_timestamp_end_s"] * 1e9),
            )
            yield contracts.URFeedback(
                provenance,
                tuple(sample["joint_positions_rad"]),
                tuple(sample["joint_velocities_rad_s"]),
                tuple(sample["joint_currents_a"]),
                tuple(sample["tcp_pose_m_rotvec_rad"]),
                sample["robot_mode"],
                sample["safety_mode"],
            )
            index += 1
            stop.wait(1 / 30)
    finally:
        receiver.disconnect()


def hande_stream(config, stop):
    """Poll the existing bridge; do not activate an inactive gripper."""
    identity = f"hande@{config['host']}:{config['port']}"
    reader = hande.Reader(config["host"], config["port"])
    try:
        # A valid full read is required before declaring this bridge ready.
        values, started = reader.read()
        yield {
            "source_id": identity,
            "transport": "robotiq_urcap_get",
            "identity_verified": False,
            "registers": list(hande.REGISTERS),
            "freshness": "socket_reply_only_no_device_timestamp",
        }
        index = 0
        while not stop.is_set():
            yield contracts.HandEFeedback(
                _provenance(identity, index, None),
                values,
                started,
            )
            index += 1
            if stop.wait(0.1):
                break
            values, started = reader.read()
    finally:
        reader.close()


def synthetic_stream(device, stop):
    """Explicit software fixtures; never selected for a hardware recording."""
    identity = "synthetic-" + device
    yield {"source_id": identity, "transport": "synthetic"}
    index = 0
    while not stop.is_set():
        if device == "ur":
            yield contracts.URFeedback(
                _provenance(identity, index, index * 33_333_333, True),
                (0.1,) * 6,
                (0.0,) * 6,
                (0.2,) * 6,
                (0.3,) * 6,
                3,
                7,
            )
        else:
            started = time.monotonic_ns()
            yield contracts.HandEFeedback(
                _provenance(identity, index, None, True),
                tuple(zip(hande.REGISTERS, (3, 0, 0, 0, 0, 0))),
                started,
            )
        index += 1
        stop.wait(1 / 30 if device == "ur" else 0.1)
