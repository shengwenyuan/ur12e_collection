# M03: Powered UR12e Read-Only State Check

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: M03-A01 short read-only check PASS; motion acceptance NOT RUN, 2026-09-11.

The user reports that the physical UR12e is powered and started in Manual mode,
and explicitly prohibits all control signals. Use the existing `devices ur`
diagnostic from the verified current image on the collection PC. Read fixed
Dashboard identity/status queries and RTDE outputs only, for five seconds.
Do not instantiate RTDEControl/IO, send URScript, load/play/stop a program,
change mode, unlock/reset safety, change speed, or access the Hand-E/cameras.

Expected endpoint: `10.18.1.106`; expected serial: `20255100083`.
Capture actual software/model replies, joint positions/velocities/currents,
TCP pose, robot/safety codes and timestamps. Preserve original replies and
sampling limitations. Local/Remote and Manual/Automatic are distinct concepts;
do not infer one from the other. Results are a short M03-A01 readback check,
not control, collision clearance, physical HOME or sustained recording acceptance.


## Results

The current image `a3d22d1ffa6c` on `ur12e-flexlab` reached the controller using
only Dashboard status queries and RTDE output subscription. Both connections
were closed after bounded reads. No control/IO SDK, URScript, program/mode/speed
change, safety reset, gripper command or camera acquisition was invoked.

| Field | Actual reply or measurement |
| --- | --- |
| Serial | `20255100083` (matches the registered unit) |
| Software | `URSoftware 5.22.1.1214860 (Jun 05 2025)` |
| Model query | `UR10` (preserve raw value; do not rewrite the user's physical UR12e identity) |
| Robot mode | `RUNNING`, RTDE code 7 |
| Safety | `NORMAL`, RTDE code 1 |
| Operational mode | `MANUAL` |
| Remote control | `false` (Local) |
| Program state | `STOPPED <unnamed>` |
| Program running | `false` |
| Diagnostic sample count | 150 over 4.984 s of observed receipt span |
| Maximum absolute measured joint speed | 0.000025588 rad/s |
| Maximum per-joint position span | 0.004864 degrees |

Last measured joints in base/shoulder/elbow/wrist1/wrist2/wrist3 order, degrees:
`[0.002, -90.985, -88.885, -89.625, 89.628, -0.370]`.
The maximum difference from configured `[0, -90, -90, -90, 90, 0]` HOME is
1.114623 degrees. This is an observation, not a HOME-arrival acceptance or a
request to correct the posture. No target or station configuration was updated.

Last active TCP in UR base, meters plus rotation vector in radians:
`[0.702621, -0.175200, 0.680690, 2.227736, -2.212964, 0.023727]`.
The controller's active TCP offset was not read; do not treat this as a verified
flange pose or a calibrated wrist-camera transform. Motor currents remain raw
amperes, not joint torque estimates.

Controller timestamps advance throughout. One of the 150 getter samples spans a
controller update (start/end timestamp mismatch); its raw brackets are retained
and it is not a strictly coherent sample. The final reported pose has matching
brackets. This 30 Hz diagnostic reads a 125 Hz receive interface and does not
qualify sustained capture timing, control-loop timing or an atomic RTDE packet.

A separate bounded read-only query confirmed `get operational mode`,
`programState` and `running` after identity verification. The vendor documents
these as status queries; robot mode and program execution are separate fields.
See the official [Dashboard reference](https://www.universal-robots.com/manuals/EN/HTML/SW5_25/Content/prod-dashboard/Dashboard_table.htm).
The one-shot script remains diagnostic evidence rather than a mainline interface
change. The current image and fixed application query allowlist are unchanged.

Remote evidence: `/home/robot2026fall/ur12e-readonly-20260911/`.
Local evidence: `artifacts/ur-readonly-20260911/ur-state.json`,
`operational-mode.json`, `summary.json`, logs and the exact extra-query script.
Physical model-query naming (`UR10` versus the user's UR12e unit) is retained as
an unresolved API naming discrepancy; no control profile is selected from it.
Full M03 control, M06 route/hold and M09 teleoperation acceptance remain NOT RUN
on physical hardware. The user's prohibition on physical control stays in force.
