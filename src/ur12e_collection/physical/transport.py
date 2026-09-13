"""Physical UR and Hand-E execution behind the shared motion owner."""

import contextlib
import dataclasses
import time

from ur12e_collection.control import model, settling
from ur12e_collection.control.ur import URTransport, read_state
from ur12e_collection.physical import preflight, stopping, tool


@dataclasses.dataclass(frozen=True)
class Feedback(model.State):
    """UR readback with separately acquired raw tool feedback."""

    gripper_registers: tuple = ()
    gripper_acquired_ns: int = 0
    gripper_open: bool = False


class Transport(URTransport):
    """One arm SDK writer; the independent tool worker owns its socket."""

    # The adapter owns one composite device and its evidence callback.
    # pylint: disable=too-many-arguments
    def __init__(self, control, receiver, worker, config, emit=None):
        super().__init__(
            control,
            receiver,
            owns_receiver=False,
            stop_deceleration=config["follower"]["stop_deceleration"],
        )
        self.emit = emit
        self.tool = worker
        self.config = config
        self.watchdog_enabled = False
        self.stopping = None
        self.halted = False
        self.protected = False

    def event(self, name, **values):
        """Evidence failure must never prevent a stop request."""
        if self.emit:
            with contextlib.suppress(Exception):
                self.emit(name, **values)

    def enable_watchdog(self):
        """Arm liveness after source startup and before motion."""
        if not self.control.setWatchdog(5.0) or not self.control.kickWatchdog():
            raise model.ControlError("controller watchdog setup failed")
        self.watchdog_enabled = True

    def _observe(self):
        """Retain protective state even after the SDK program disappears."""
        state = read_state(self.receiver)
        if state.safety_mode == 3 and not self.protected:
            self.protected = True
            self.tool.hold()
            self.event("protective_stop", feedback=state)
        return state

    def read(self):
        state = self._observe()
        if self.protected:
            return state
        if self.stopping is not None:
            self.stopping.check()
        if not self.control.isConnected():
            raise model.ControlError("UR connection lost")
        reading = self.tool.view()
        values = dict(reading.registers)
        opened = (
            values["POS"] <= self.config["gripper"]["open_tolerance"]
            and values["OBJ"] != 0
        )
        return Feedback(
            **dataclasses.asdict(state),
            gripper_registers=reading.registers,
            gripper_acquired_ns=reading.acquired_ns,
            gripper_open=opened,
        )

    def heartbeat(self):
        """A stopping worker exclusively owns SDK writes until completion."""
        if self.stopping is not None and not self.stopping.done.is_set():
            return
        super().heartbeat()

    def move(self, q, speed, acceleration, gripper_position=None):
        """HOME never opens the real tool."""
        if gripper_position is not None:
            raise model.ControlError("physical HOME must not command Hand-E")
        self.halted = False
        super().move(q, speed, acceleration)

    def servo(self, q, gripper_position=None):
        """Only dispatch a tool request after the arm accepts its target."""
        if self.stopping is not None and not self.stopping.done.is_set():
            raise model.ControlError("stop still owns the SDK")
        super().servo(q)
        self.halted = False
        if gripper_position is not None:
            self.tool.offer(gripper_position)

    # Deferred SDK/application protection-scope review lives in the M09 plan.
    # Controller safety thresholds remain separate and unchanged.
    def stop(self, servo):
        """Drop pending tool work and dispatch ordinary arm deceleration."""
        self.tool.hold()
        if self.protected:
            self.halted = True
            return  # UR owns this stop; no SDK program restart or stop retry.
        if not self.halted:
            self.event("stop_request", servo=servo)
            deceleration = self.config["follower"][
                "servo_stop_deceleration_m_s2" if servo else "stop_deceleration"
            ]
            self.stopping = stopping.Stop(
                self.control, servo, deceleration, self.event
            )
            self.halted = True
            self.stopping.start()

    def close(self):
        """Verify actual standstill before releasing the SDK program."""
        if self.closed:
            return
        try:
            self._observe()
            if not self.halted:
                self.stop(False)
            state = self._confirm_standstill()
            if self.protected:
                self.event("protective_stop_confirmed", feedback=state)
                return
            if self.stopping is not None:
                self.stopping.join()
            self.control.stopScript()
            self.observe_hold(state.q)
        finally:
            try:
                if (
                    self.stopping is not None
                    and not self.stopping.done.is_set()
                ):
                    self.stopping.join()
                if self.protected:
                    self.control.disconnect()
                else:
                    super().close()
            finally:
                try:
                    self.receiver.disconnect()
                finally:
                    self.closed = True
                    self.tool.close()

    def _confirm_standstill(self):
        """Confirm from outputs without requiring a running SDK program."""
        stable = settling.Standstill()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = self._observe()
            if self.watchdog_enabled and not self.protected:
                self.heartbeat()
            if stable.update(state.qd, state.timestamp, time.monotonic_ns()):
                self.event("standstill_confirmed", feedback=state)
                break
            self.event("stop_feedback", feedback=state)
            time.sleep(0.008)
        else:
            raise model.ControlError(
                "stop unconfirmed; operator intervention required"
            )
        return state

    def observe_hold(self, anchor):
        """Output-only observation outlives the stopped control script."""
        started = time.monotonic()
        until = started + 30
        released = False
        previous, progressing = None, time.monotonic()
        while time.monotonic() < until:
            state = read_state(self.receiver)
            now = time.monotonic()
            if previous is None or state.timestamp > previous:
                progressing = now
            elif state.timestamp < previous:
                raise model.ControlError("feedback restarted after stop")
            previous = state.timestamp
            self.event("held_feedback", feedback=state)
            released |= state.holding_allowed
            valid_runtime = state.runtime_state == 1 or (
                not released
                and now - started <= 1
                and state.runtime_state in (0, 2)
            )
            if (
                now - progressing > 0.25
                or not valid_runtime
                or (state.robot_mode, state.safety_mode) != (7, 1)
                or max(map(abs, state.qd)) > settling.HOLD_SPEED
                or model.distance(anchor, state.q) > settling.HOLD_DRIFT
            ):
                raise model.ControlError("post-stop hold not confirmed")
            time.sleep(0.008)
        self.event("observation_complete")


def open_transport(config, emit=None):
    """Called only by explicit operator execution, never by preflight."""
    if config["follower"].get("servo_stop_deceleration_m_s2") is None:
        raise model.ControlError(
            "servo stop parameter needs operator alignment"
        )
    preflight.identity(config, True)
    rx = preflight.receiver(config["follower"]["host"])
    worker = tool.Worker(config["follower"]["host"], config["gripper"])
    control = None
    try:
        before = preflight.stationary(rx, config["limits"])
        worker.start()
        # The owner is now explicitly authorized to upload its idle SDK script.
        import rtde_control  # pylint: disable=import-outside-toplevel,import-error

        control = rtde_control.RTDEControlInterface(
            config["follower"]["host"],
            120.0,
            rtde_control.RTDEControlInterface.FLAG_UPLOAD_SCRIPT
            | rtde_control.RTDEControlInterface.FLAG_UPPER_RANGE_REGISTERS,
        )
        transport = Transport(control, rx, worker, config, emit)
        preflight.handover(
            transport.read, before, config["limits"], transport.event
        )
        return transport
    except BaseException:
        try:
            if control is not None:
                control.stopScript()
                control.disconnect()
        finally:
            rx.disconnect()
            worker.close()
        raise
