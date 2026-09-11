"""Receive actual URSim state only; never initialize or own robot motion."""

import json
import sys
import time

import rtde_receive  # pylint: disable=import-error

from ur12e_collection import ur
from ur12e_collection.simulation import connection, profile


def run():
    """Verify the isolated peer and stream measured radians at 30 Hz."""
    address = connection.verify_boundary()
    identity = ur.dashboard(address)
    replies = identity["responses"]
    if (
        identity["state"] != "available"
        or replies.get("get serial number") != profile.SERIAL
        or not replies.get("PolyscopeVersion", "").startswith(profile.VERSION)
    ):
        raise ValueError("read-only viewer simulator identity differs")
    receiver = rtde_receive.RTDEReceiveInterface(
        address, 30.0, ["timestamp", "actual_q"]
    )
    try:
        while True:
            before = receiver.getTimestamp()
            q = receiver.getActualQ()
            after = receiver.getTimestamp()
            if before == after:
                print(
                    json.dumps({"timestamp_s": after, "actual_q": q}),
                    flush=True,
                )
            time.sleep(1 / 30)
    finally:
        receiver.disconnect()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
    except Exception as error:  # pylint: disable=broad-exception-caught
        print(f"Read-only viewer: {error}", file=sys.stderr)
        sys.exit(1)
