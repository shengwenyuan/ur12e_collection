# Nominal UR12e kinematics

`ur12e.urdf` is the unchanged generated nominal model used by the height-aware
teleoperation acceptance. SHA256:
`51d3a3812a81c2a3d0ff2423a0aaab7c7547c19019297daba865a3c4bb04dd60`.

Provenance: `ur12e-sim` asset manifest, generated from Universal Robots
`Universal_Robots_ROS2_Description`, Jazzy revision
`39242984dc8d1fff9584c922c17c69c58df3591d`, UR12e configuration.
The upstream BSD-3-Clause license is retained in `LICENSE`.

The collector reads only the ordered six-joint root-to-flange chain. Mesh paths
remain as upstream references and are never loaded. No meshes, Isaac runtime or
sibling repository are required. This is nominal geometry, not factory-calibrated
kinematics. The 154 mm engineering reference belongs to this exact model; it is
not a measured tabletop height or a collision-avoidance boundary.

Paths are relative to the selected teleop JSON. From `config/teleop.ur.json`, use
`kinematics/ur12e.urdf`; from `config/local/teleop.ur.json`, use
`../kinematics/ur12e.urdf`. Keep the digest pinned in either case.
