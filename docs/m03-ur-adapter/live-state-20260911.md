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

## Pre-motion static recheck (2026-09-11)

The user authorized static inspection only. Every subsequent test must first
align its verification points and operator procedure. The user owns all physical
start, motion and mode changes; the assistant must not send control commands.
This recheck reused the existing bounded `ur.receive(host, 30.0)` function in an
isolated diagnostic script because the public probe command caps each run at
10 seconds. No mainline code or station configuration changed.

The collection PC still uses image `a3d22d1ffa6c` and release
`/home/robot2026fall/ur12e-unified-bbc56a8`. No Docker containers were running
before or after the diagnostic. The station configuration hash remains
`17c3b9e2e505972f90a2dc0add6ea64f23cdd830dda1154f60c015b24424bb9c`.
Its production device identities and READY vector are still unset and
`motion_accepted` is false. This probe supplied the known address explicitly;
its success does not establish a fully bound production station.

| Verification | Result |
| --- | --- |
| Identity and mode | PASS: serial `20255100083`, software unchanged; Manual/Local and stopped program before and after; robot mode 7 and safety mode 1 throughout |
| Static observation | PASS within this diagnostic: 896 samples over 29.986 s; peak absolute joint speed 0.000149742 rad/s; maximum joint position span 0.006803 degrees |
| READY numerical comparison | Maximum error 0.002873 degrees, below the existing 0.01 rad arrival tolerance; no motion, path, or powered-hold acceptance inferred |
| Feedback continuity | FAIL for the requested continuously advancing diagnostic: 27 repeated timestamps across 13 bursts, no backwards timestamps; longest observed unchanged span 133.95 ms; maximum source-time jump 256 ms |
| Getter coherence | Two samples crossed controller timestamp updates; raw brackets retained, not atomic packet observations |
| Physical installation and pendant comparison | NOT RUN: mounting, clearance, TCP/payload/CoG, safety settings, speed slider and independent pendant readout require operator verification |
| Physical control and stopping | NOT RUN; prohibited |

Last coherent joint angles, degrees:
`[-0.000045, -89.999494, -89.997127, -89.999125, 89.998944, -0.001083]`.
The diagnostic host read loop remained regular (maximum receipt interval
34.601 ms). A controller timestamp jump is not itself a measurement of network
latency or proof of lost RTDE packets. Further receive-path diagnosis is required.

The PC routes the controller through Wi-Fi `wlp3s0`, gateway `10.245.128.1`,
source address `10.245.129.12`. A five-request ICMP check had no loss and RTT
2.957/21.246/86.897 ms minimum/average/maximum. Network jitter is a candidate,
not an established cause of the repeated RTDE timestamps. Do not broaden motion
freshness thresholds to hide this observation.

Evidence is in local `artifacts/ur-static-20260911/` and remote
`/home/robot2026fall/ur12e-static-20260911/`: exact `check.py`, `raw.json`,
`summary.json`, and `check.log`. The local directory also preserves the route.
Next proposed step is a separately aligned read-only connectivity comparison,
preferably over a verified wired path if available. Do not proceed to motion
based on this static result.

## Extended receive-only preflight (2026-09-11)

The user requested further physical robot verification while retaining ownership
of all control starts and prohibiting assistant-issued control signals. A
10-second diagnostic used only Dashboard status queries and an explicit RTDE
output recipe through `RTDEReceiveInterface`. No control/IO SDK, URScript,
program load/play/stop, mode change or configuration write was performed.
The same immutable image ran in a non-root read-only container with no Linux
capabilities; it exited successfully and left no running containers.

| Verification | Result |
| --- | --- |
| Identity/modes | PASS: registered serial; Manual/Local, NORMAL, program stopped before and after; runtime state 1 throughout |
| Loaded program | `/programs/<unnamed>.urp`; contents and Home-node parameters not inspected |
| Short feedback continuity | PASS for this 10-second window: 299 samples over 9.990 s, zero repeated/backwards source timestamps, maximum source interval 40 ms |
| READY numerical comparison | Maximum error 0.002873 degrees; no commanded arrival or route validation |
| Static actual values | Peak absolute joint speed 0.000038374 rad/s; peak TCP translation speed 0.000026877 m/s |
| Controller target derivatives | All observed target joint velocities and accelerations zero; these are output observations, not commands |
| Configured payload | 5.0 kg; CoG `[0, 0, 0]` m; inertia `[0.022505, 0.022505, 0.022505, 0, 0, 0]` kg m² |
| Speed scaling | `speed_scaling=0`, `target_speed_fraction=1` throughout stopped program; not a verified speed-slider setting or motion-speed acceptance |
| Joint temperatures | Last observation `[27.25, 27.5, 30, 31, 32.25, 32.75]` degrees C; informational only |
| Active TCP offset | NOT RUN: installed receive SDK exposes no getter; pendant inspection remains required; no control SDK was instantiated to obtain it |

Configured payload values are controller settings, not a measurement of the
attached Hand-E, adapter, camera or their combined center of gravity. The next
operator check is to inspect the active installation TCP and payload/CoG values
and reconcile them with the actual assembly before any motion test. Do not
substitute estimated values or write a new payload automatically. No pendant
program should be started solely because this read-only preflight passed.

This successful short window does not resolve the earlier 30-second Wi-Fi
continuity failure. Keep that observation open. Core q/qd/TCP getter reads used
timestamp brackets; one sample's additional diagnostic getters crossed a later
controller update and remains marked in the raw evidence. No atomic full-record
or camera synchronization acceptance is inferred.

Evidence: local `artifacts/ur-preflight-extended-20260911/` and remote
`/home/robot2026fall/ur12e-preflight-extended-20260911/`, containing the exact
script, raw samples, summary and log. Output-field meanings and units follow the
[official RTDE guide](https://docs.universal-robots.com/tutorials/communication-protocol-tutorials/rtde-guide.html).

### Operator TCP/payload clarification (2026-09-11)

The operator confirms that all active TCP translation/orientation values are
zero. The current TCP is therefore the flange coordinate frame, not a verified
fingertip/grasp-center frame. Keep existing feedback labeled base-to-active-TCP;
with this reported setting it refers to the flange. No TCP setting was changed.
The operator reports that the 5 kg payload setting has been used for a long time.
Retain it as the existing site configuration; this history does not independently
measure the mass, CoG or inertia of the present complete mounted assembly.
These findings do not block read-only observation or establish motion acceptance.
