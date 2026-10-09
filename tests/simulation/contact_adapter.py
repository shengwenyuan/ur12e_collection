"""Test-only contact logging around the unchanged native scene driver."""

import dataclasses
import importlib.util
import json


class Driver:
    """Record solver acquisitions and contact evidence; never replace feedback."""

    def __init__(self, stage, root, config):
        from omni.physx import get_physx_simulation_interface
        from pxr import PhysxSchema, UsdPhysics, PhysicsSchemaTools

        for prim in stage.Traverse():
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                PhysxSchema.PhysxContactReportAPI.Apply(
                    prim
                ).CreateThresholdAttr(0)
        self.contacts = []

        def capture(headers, data):
            for header in headers:
                points = data[
                    header.contact_data_offset : header.contact_data_offset
                    + header.num_contact_data
                ]
                self.contacts.append(
                    {
                        "actors": [
                            str(PhysicsSchemaTools.intToSdfPath(actor))
                            for actor in (header.actor0, header.actor1)
                        ],
                        "type": str(header.type),
                        "points": [
                            {
                                "position": list(p.position),
                                "impulse": list(p.impulse),
                                "separation": p.separation,
                            }
                            for p in points
                        ],
                    }
                )

        self.subscription = (
            get_physx_simulation_interface().subscribe_contact_report_events(
                capture
            )
        )
        spec = importlib.util.spec_from_file_location(
            "native_physics",
            config.get("diagnostic_adapter", root / "runtime/physical.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.driver = module.Driver(stage, root, config)
        output = config["follower"]["endpoint"].parent
        self.stream = (output / "solver.jsonl").open("w")
        # Diagnostic only: independently confirm PhysX parsed a fixed root.
        robot = self.driver.robot
        view = getattr(robot, "_articulation_view", robot)._physics_view
        self.view = view
        (output / "topology.json").write_text(
            json.dumps(
                {
                    "fixed_base": view.shared_metatype.fixed_base,
                    "gravity_dofs": len(
                        view.get_gravity_compensation_forces()[0]
                    ),
                    "link_names": view.shared_metatype.link_names,
                    "articulation": self.driver.layout["articulation"],
                },
                indent=2,
            )
        )

    def step(self, q, fingers):
        sample = self.driver.step(q, fingers)
        row = {"sample": dataclasses.asdict(sample), "contacts": self.contacts}
        if sample.sequence % 120 == 0:
            row["link_transforms"] = self.view.get_link_transforms()[0].tolist()
        self.stream.write(json.dumps(row) + "\n")
        self.contacts.clear()
        return sample

    def read(self):
        return self.driver.read()

    def is_playing(self):
        return self.driver.is_playing()

    def render(self):
        self.driver.render()

    def close(self):
        self.subscription = None
        self.stream.close()
        self.driver.close()
