"""Bind independent leader acquisitions to one shared control interval."""

import dataclasses

from ur12e_collection.control import conditioning, model
from ur12e_collection.leader import episode


class Input:
    """Consume source views; freshness uses original acquisition time."""

    def __init__(self, source, calibration, limits, follower, now_ns):
        self.source = source
        self.calibration = calibration
        self.limits = limits
        samples = source.samples(now_ns)
        self.mapper = episode.EpisodeMapper(
            calibration, limits, samples, follower, now_ns
        )
        self.reading = samples[-1]
        self.desired = self.mapper.first()
        seed = model.Target(limits.ready, 0, now_ns, "gello")
        self.conditioner = conditioning.Conditioner(limits, seed)
        self.initial = True
        self.closed = False

    def context(self):
        """Freeze both the episode baseline and its fixed calibration."""
        return self.mapper.context() | {
            "calibration": self.calibration.document(),
            "input_origin": self.source.origin,
            "limits": dataclasses.asdict(self.limits),
        }

    def sample(self, now_ns):
        """Reuse fresh intent with separate source and command identities."""
        if self.closed:
            raise model.ControlError("leader ownership ended")
        try:
            return self._sample(now_ns)
        except Exception:
            self.close()
            raise

    def _sample(self, now_ns):
        readings = self.source.samples(now_ns)
        sample = readings[-1]
        if sample == self.reading:
            if now_ns - sample.start_ns > 100_000_000:
                raise model.ControlError("leader input is stale")
        else:
            self.desired = self.mapper.target(sample, now_ns)
            self.reading = sample
        if self.initial:
            self.initial = False
            return self.conditioner.target
        return self.conditioner.step(self.desired.q, now_ns)

    def evidence(self):
        """Retain raw source identity for independent command audits."""
        return dataclasses.asdict(self.reading)

    def close(self):
        """Invalidate the immutable baseline without writing any motor."""
        self.closed = True
        self.mapper.stop()
