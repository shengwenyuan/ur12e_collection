"""Translate measured control events without changing their clock domains."""

import collections

from ur12e_collection import contracts
from ur12e_collection.control.model import State, Target


class Records:
    """Independent sequence counters scoped to one recorded episode."""

    def __init__(self, context: dict, *, simulated: bool):
        self.context = context
        self.simulated = simulated
        self.sequences = collections.Counter()
        self.last_feedback_stamp = None

    def _provenance(self, kind, source, stamp, receipt, clock):
        sequence = self.sequences[kind]
        self.sequences[kind] += 1
        return contracts.Provenance(
            self.context[source],
            sequence,
            contracts.SampleTime(stamp, clock, receipt),
            self.simulated,
        )

    def authority(self, action: str, reason: str, now_ns: int, context=None):
        """Mark the exact receipt boundary, including the exclusive stop end."""
        return contracts.AuthorityEvent(
            self._provenance(
                "authority_event",
                "owner_id",
                now_ns,
                now_ns,
                "host_monotonic",
            ),
            action,
            reason,
            context,
        )

    def intent(self, target: Target, leader=None):
        """Preserve leader intent before transport acceptance."""
        if target.source_id != self.context["leader_id"]:
            raise ValueError("recorded leader differs from active source")
        return contracts.LeaderIntent(
            self._provenance(
                "leader_intent",
                "leader_id",
                target.created_ns,
                target.created_ns,
                "host_monotonic",
            ),
            target.q if leader is None else leader.desired.q,
            None,
            None if leader is None else leader.evidence(),
        )

    def sent(self, target: Target, sent_ns: int):
        """Call only after the SDK has accepted the actual servo command."""
        return contracts.SentCommand(
            self._provenance(
                "sent_command",
                "command_id",
                sent_ns,
                sent_ns,
                "host_monotonic",
            ),
            target.q,
            None,
        )

    def feedback(self, state: State) -> tuple:
        """Keep measured samples distinct; gripper data stays absent."""
        if state.timestamp == self.last_feedback_stamp:
            return ()
        if state.currents is None or state.tcp is None:
            raise ValueError("recorded UR feedback requires complete readback")
        stamp = round(state.timestamp * 1e9)
        result = []
        for kind in ("follower_state", "ur_feedback"):
            p = self._provenance(
                kind,
                "arm_id",
                stamp,
                state.received_ns,
                "ur_controller_uptime",
            )
            result.append(
                contracts.FollowerState(p, state.q, None)
                if kind == "follower_state"
                else contracts.URFeedback(
                    p,
                    state.q,
                    state.qd,
                    state.currents,
                    state.tcp,
                    state.robot_mode,
                    state.safety_mode,
                )
            )
        self.last_feedback_stamp = state.timestamp
        return tuple(result)
