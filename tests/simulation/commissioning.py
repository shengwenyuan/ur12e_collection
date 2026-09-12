"""Physical adapter braking checks using verified URSim and a tool fixture."""

import dataclasses
import json
import math
import pathlib
import time

from ur12e_collection.control import conditioning, model, owner
from ur12e_collection.physical import tool
from ur12e_collection.physical.transport import Transport
from ur12e_collection.simulation import connection, profile


class Tool:
    """Explicit test fixture: no Hand-E socket or physical input exists."""

    def view(self):
        return tool.Reading(
            (("POS", 0), ("PRE", 0), ("OBJ", 3)), time.monotonic_ns()
        )

    def hold(self):
        pass

    def offer(self, _position):
        pass

    def close(self):
        pass


def wait(controller):
    while controller.state != "hold":
        controller.tick(time.monotonic_ns())
        time.sleep(1 / 120)


def trial(controller, signs):
    controller.tick(time.monotonic_ns())
    now = time.monotonic_ns()
    seed = model.Target(controller.progress.feedback.q, 0, now)
    smooth = conditioning.Conditioner(controller.limits, seed)
    controller.engage(seed, now)
    end = time.monotonic() + 1.5
    while time.monotonic() < end:
        controller.tick(time.monotonic_ns())
        target = smooth.step(
            tuple(q + sign * math.radians(4) for q, sign in zip(seed.q, signs)),
            time.monotonic_ns(),
        )
        controller.follow(target, time.monotonic_ns())
        time.sleep(1 / 120)
    velocity = controller.progress.feedback.qd
    assert max(map(abs, velocity)) > math.radians(1), velocity
    requested = time.monotonic()
    controller.halt(time.monotonic_ns())
    dispatch_s = time.monotonic() - requested
    wait(controller)
    assert dispatch_s < 0.1
    stopped_s = time.monotonic() - requested
    assert stopped_s < 2
    assert controller.transport.control.isProgramRunning()
    return {
        "moving_qd": velocity,
        "dispatch_s": dispatch_s,
        "settled_s": stopped_s,
    }


def run():
    events, results = [], []
    path = pathlib.Path("/results") / f"commissioning-{time.time_ns()}.json"
    with connection.open_controller() as original:
        setup = owner.Controller(original, profile.LIMITS)
        setup.tick(time.monotonic_ns())
        setup.go_ready(time.monotonic_ns())
        wait(setup)
        limits = dataclasses.replace(
            profile.LIMITS,
            speed=math.radians(2),
            acceleration=math.radians(2),
            ready_speed=math.radians(1),
            ready_acceleration=math.radians(2),
            arrival=math.radians(0.1),
            stopped_speed=math.radians(0.01),
        )
        config = {
            "follower": {
                "stop_deceleration": math.radians(2),
                "servo_stop_deceleration_m_s2": 0.1,
            },
            "gripper": {"open_tolerance": 5},
        }
        device = Transport(
            original.control,
            original.receiver,
            Tool(),
            config,
            lambda event, **values: events.append(
                {"event": event, "ns": time.monotonic_ns(), **values}
            ),
        )
        device.enable_watchdog()
        controller = owner.Controller(device, limits)
        try:
            for signs in [(1,) * 6, (-1, 1, -1, 1, -1, 1)]:
                results.append(trial(controller, signs))
                controller.go_ready(time.monotonic_ns())
                wait(controller)
            # Exercise cancellable SDK HOME away from its target.
            state = controller.tick(time.monotonic_ns())
            controller.route(
                (tuple(q + math.radians(3) for q in state.q),),
                state.q,
                time.monotonic_ns(),
                ready=True,
            )
            until = time.monotonic() + 1.5
            while time.monotonic() < until:
                controller.tick(time.monotonic_ns())
                time.sleep(1 / 120)
            controller.halt(time.monotonic_ns())
            wait(controller)
            controller.close()  # Includes 30 seconds of actual held readback.
        finally:
            path.write_text(
                json.dumps(
                    {"trials": results, "events": events},
                    default=dataclasses.asdict,
                    indent=2,
                )
            )
            if not device.closed:
                device.close()
        assert events[-1]["event"] == "observation_complete"
        print(
            json.dumps(
                {"PASS": True, "trials": results, "evidence": str(path)}
            ),
            flush=True,
        )


if __name__ == "__main__":
    run()
