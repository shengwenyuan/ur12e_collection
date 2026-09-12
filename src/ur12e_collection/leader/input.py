"""Bind independent leader acquisitions to one shared control interval."""

import dataclasses

from ur12e_collection.control import conditioning, model
from ur12e_collection.leader import episode


# One immutable mapping interval retains raw and conditioned state separately.
# pylint: disable=too-many-instance-attributes
class Input:
    """Consume source views; freshness uses original acquisition time."""

    # Acquisition validity is independent of follower feedback timing.
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        source,
        calibration,
        limits,
        follower,
        now_ns,
        *,
        freshness_ns=100_000_000,
        guards=None,
    ):
        self.guards = guards
        self.source = source
        self.calibration = calibration
        self.limits = limits
        self.freshness_ns = min(limits.freshness_ns, freshness_ns)
        samples = source.samples(now_ns)
        self.mapper = episode.EpisodeMapper(
            calibration,
            limits,
            samples,
            follower,
            now_ns,
            freshness_ns=freshness_ns,
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
        if not readings:
            raise model.ControlError("leader input is unavailable")
        sample = readings[-1]
        if sample == self.reading:
            if now_ns - sample.start_ns > self.freshness_ns:
                raise model.ControlError("leader input is stale")
        else:
            if self.guards is not None:
                previous = self.reading
                for reading in readings:
                    if reading.sequence > previous.sequence:
                        self.guards.input(previous, reading)
                        previous = reading
            self.desired = self.mapper.target(sample, now_ns)
            self.reading = sample
        if self.initial:
            self.initial = False
            return self.conditioner.target
        if self.guards is not None:
            self.guards.intent(self.desired.q, self.conditioner.target.q)
        return self.conditioner.step(self.desired.q, now_ns)

    def evidence(self):
        """Retain raw source identity for independent command audits."""
        return dataclasses.asdict(self.reading)

    def close(self):
        """Invalidate the immutable baseline without writing any motor."""
        self.closed = True
        self.mapper.stop()
