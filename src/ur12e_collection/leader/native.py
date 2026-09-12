"""Native same-host leader input for mainline teleoperation."""

import collections

from ur12e_collection.leader import source


class Leader:
    """Maintain a stable-reference window without motor writes or relays."""

    origin = "physical_gello"

    def __init__(self, device, baudrate):
        self.reader = source.Reader(device, baudrate)
        self.recent = collections.deque(maxlen=16)

    def start(self):
        """Inventory and acquire using the existing read-only source."""
        self.reader.start()

    def samples(self, now_ns):
        """Drain backlog while preserving original acquisition time."""
        view = self.reader.mailbox.view()
        if any(view.health.integers(64, 1)):
            raise ValueError("manual-support leader requires torque off")
        self.recent.extend(
            motion.sample for motion in self.reader.mailbox.drain()
        )
        return tuple(
            sample
            for sample in self.recent
            if sample.end_ns <= now_ns
            and now_ns - sample.start_ns <= 80_000_000
        )

    def close(self):
        """Close the serial reader without changing motor registers."""
        self.reader.close()
