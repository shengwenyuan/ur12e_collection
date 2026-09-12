"""Fixed-step physical follower, independent of viewport cadence."""

import importlib.util
import json
import time

from ur12e_collection.followers import local, physics


def run(app, stage, config, args):
    """Load the configured scene adapter inside Isaac."""
    spec = importlib.util.spec_from_file_location(
        "collection_physical_scene", config["scene"]["adapter"]
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    driver = module.Driver(stage, config["scene"]["root"], config)
    service = None
    try:
        engine = physics.Engine(
            config["limits"],
            time.monotonic(),
            driver,
            config["physics"],
            config["gripper"]["aperture_speed_m_s"] / 0.05 * 255,
        )
        service = local.Service(
            config["follower"]["endpoint"], config["limits"], engine=engine
        )
        loop(app, driver, service, config, args)
    finally:
        if service is not None:
            service.close()
        driver.close()


def loop(app, driver, service, config, args):
    """Step once per cycle; never burst stale targets to catch up."""
    started = reported = rendered = time.monotonic()
    dt = 1 / config["physics"].step_hz
    while app.is_running():
        began = time.monotonic()
        if args.duration and began - started >= args.duration:
            break
        service.receive()
        try:
            service.engine.update(began)
        finally:
            # A fault packet retains the last actual acquisition clock.
            service.publish()
        now = time.monotonic()
        if (
            not args.headless
            and now - rendered >= 1 / config["scene"]["display_hz"]
        ):
            driver.render()
            rendered = time.monotonic()
        if now - reported >= 1:
            result = {
                **service.engine.snapshot(now),
                "owner": service.epoch,
                "simulated": True,
                "physics_running": driver.is_playing(),
                "wall_elapsed_s": now - started,
                "real_time_factor": service.engine.sample.time_s
                / (now - started),
            }
            if args.report:
                args.report.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result), flush=True)
            reported = now
        time.sleep(max(0, dt - (time.monotonic() - began)))
