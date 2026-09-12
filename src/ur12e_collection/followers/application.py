"""Native Isaac application; scene execution is selected at its boundary."""

import importlib.util
import json
import math
import time

from ur12e_collection.followers import config as configuration
from ur12e_collection.followers import local
from ur12e_collection.followers import physical_application


def scene_adapter(path, stage, root):
    """Load the explicitly configured scene adapter after Kit initialization."""
    spec = importlib.util.spec_from_file_location("collection_scene_pose", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Pose(stage, root)


def run(args):
    """Execute received commands on this scene, then publish simulated state."""
    if not math.isfinite(args.duration) or args.duration < 0:
        raise ValueError("duration must be finite and nonnegative")
    config = configuration.load(args.config)
    if config["follower"]["backend"] == "isaac_physics" and args.capture:
        raise ValueError("physical follower capture is not implemented")
    # All rendering imports must follow SimulationApp startup.
    # pylint: disable=import-outside-toplevel,import-error
    from isaacsim import SimulationApp

    app = SimulationApp(
        {
            "headless": args.headless,
            "width": 1280,
            "height": 720,
            "window_width": 1440,
            "window_height": 900,
            "open_usd": str(config["scene"]["entrypoint"]),
            "multi_gpu": False,
        }
    )
    try:
        import omni.timeline
        import omni.usd
        from omni.kit.viewport import utility

        viewport = utility.get_active_viewport()
        if viewport:
            viewport.camera_path = "/World/Camera"

        if config["follower"]["backend"] == "isaac_physics":
            physical_application.run(
                app, omni.usd.get_context().get_stage(), config, args
            )
            return 0
        from omni import ui

        # pylint: enable=import-outside-toplevel,import-error

        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        pose = scene_adapter(
            config["scene"]["adapter"],
            omni.usd.get_context().get_stage(),
            config["scene"]["root"],
        )
        window = ui.Window("Native Isaac follower", width=420, height=120)
        with window.frame:
            label = ui.Label("Waiting for owner", word_wrap=True)
        service = local.Service(
            config["follower"]["endpoint"],
            config["limits"],
            config["gripper"]["aperture_speed_m_s"] / 0.05 * 255,
        )
        try:
            loop(app, service, pose, label, timeline, viewport, config, args)
        finally:
            service.close()
            window.destroy()
    finally:
        app.close()
    return 0


def loop(app, service, pose, label, timeline, viewport, config, args):
    """Render at its own rate; acknowledgement follows actual stage changes."""
    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    # Explicit application-owned resources; no control state is hidden globally.
    started = reported = time.monotonic()
    capture = None
    updates = 0
    try:
        while app.is_running():
            now = time.monotonic()
            if args.duration and now - started >= args.duration:
                break
            service.receive()
            q = service.engine.update(time.monotonic())
            pose.apply(q, service.epoch, service.engine.gripper_position)
            service.publish()
            timeline.stop()
            label.text = (
                f"{'FAULT' if service.engine.fault else 'NATIVE KINEMATIC'}\n"
                f"{service.engine.fault or status(service)}\n"
                f"Gripper opening: "
                f"{50 * (1 - service.engine.gripper_position / 255):.1f} mm\n"
                "Simulated executed state | physics off"
            )
            app.update()
            updates += 1
            if args.capture and capture is None and now - started >= 2:
                # pylint: disable-next=import-outside-toplevel,import-error
                from omni.kit.viewport import utility

                capture = utility.capture_viewport_to_file(
                    viewport, str(args.capture)
                )
            if now - reported >= 1:
                report = {
                    "source": "isaac_kinematic",
                    "simulated": True,
                    "owner": service.epoch,
                    "active": service.engine.active,
                    "fault": service.engine.fault,
                    "executed_q": q,
                    "executed_qd": service.engine.qd,
                    "gripper_position": service.engine.gripper_position,
                    "gripper_aperture_m": 0.05
                    * (1 - service.engine.gripper_position / 255),
                    "physics_running": timeline.is_playing(),
                    "updates": updates,
                }
                if args.report:
                    args.report.write_text(json.dumps(report, indent=2) + "\n")
                print(json.dumps(report), flush=True)
                reported = now
            time.sleep(
                max(
                    0,
                    1 / config["scene"]["display_hz"]
                    - (time.monotonic() - now),
                )
            )
    except KeyboardInterrupt:
        pass


def status(service):
    """Describe explicit native ownership without robot-controller jargon."""
    return "Owner active" if service.peer else "Waiting for teleop"
