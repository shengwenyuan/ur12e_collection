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
        precision=None,
    ):
        self.guards = guards
        self.precision = precision
        self.reference = limits.ready
        self.mapping_state = None
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
        context = self.mapper.context() | {
            "calibration": self.calibration.document(),
            "input_origin": self.source.origin,
            "limits": dataclasses.asdict(self.limits),
        }
        if self.precision:
            context.update(
                mapping="height_relative",
                schema_version=3,
                precision=self.precision.document(),
            )
        return context

    def sample(self, now_ns, feedback=None):
        """Reuse fresh intent with separate source and command identities."""
        if self.closed:
            raise model.ControlError("leader ownership ended")
        try:
            return self._sample(now_ns, feedback)
        except Exception:
            self.close()
            raise

    def _sample(self, now_ns, feedback):
        readings = self.source.samples(now_ns)
        if not readings:
            raise model.ControlError("leader input is unavailable")
        if self.initial:
            if now_ns - self.reading.start_ns > self.freshness_ns:
                raise model.ControlError("leader input is stale")
            self.initial = False
            return self.conditioner.target
        gain = 1.0
        if self.precision:
            self.mapping_state = self.precision.observe(
                feedback, now_ns, self.freshness_ns
            )
            self.limits.check(feedback.q)
            gain = self.mapping_state["gain"]
        self._advance(readings, now_ns, gain)
        if self.guards is not None:
            self.guards.intent(self.desired.q, self.conditioner.target.q)
        accepted = self.desired.q
        if self.precision:
            dt = (now_ns - self.conditioner.target.created_ns) / 1e9
            if not 0 < dt <= self.limits.freshness_ns / 1e9:
                raise model.ControlError("precision clock stalled or jumped")
            accepted = self.precision.correct(
                self.desired.q, self.conditioner, gain, dt
            )
            self.reference = accepted
            self.mapping_state["accepted"] = accepted
        return self.conditioner.step(accepted, now_ns, gain=gain)

    def _advance(self, readings, now_ns, gain):
        """Validate retained acquisitions; consume each selected delta once."""
        sample = readings[-1]
        if sample == self.reading:
            if now_ns - sample.start_ns > self.freshness_ns:
                raise model.ControlError("leader input is stale")
            if self.precision:
                self.desired = dataclasses.replace(
                    self.desired, q=self.reference
                )
            return
        if self.guards is not None:
            previous = self.reading
            for reading in readings:
                if reading.sequence > previous.sequence:
                    self.guards.input(previous, reading)
                    previous = reading
        self.desired = self.mapper.target(
            sample,
            now_ns,
            gain=gain,
            reference=self.reference if self.precision else None,
        )
        self.reading = sample

    def evidence(self):
        """Retain raw source identity for independent command audits."""
        return dataclasses.asdict(self.reading)

    def close(self):
        """Invalidate the immutable baseline without writing any motor."""
        self.closed = True
        self.mapper.stop()
