# M03 / M05 / M06 / M09: Simulator Control Integration

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned / implementing. The user approved this concrete plan, then
confirmed bounded READY speed, shared readable control architecture, isolated
test leader inputs, and permission to bypass Hand-E simulation on 2026-09-10.
All physical control remains prohibited.
Updated: 2026-09-10. Primary owner: M06; dependencies: M01, M03, M09-M11.

## Concrete scope for alignment

1. Add a simulator-only control transport using pinned `ur_rtde 1.6.5` against
   the installed official UR12e URSim. Provide explicit initialization, joint
   motion, streaming joint targets, controlled stop and measured hold checks.
   Keep the existing physical read-only adapters unchanged.
2. Implement one control owner, configured joint/velocity/acceleration/step
   limits, source freshness, monotonic sequence checks, route start checks and
   explicit fault latching. A controller-side watchdog must stop on a killed
   or stalled host. No reconnect or automatic motion resumption.
3. Use one HOME/READY target `[0, -90, -90, -90, 90, 0]` degrees. No separate
   ZERO waypoint. This adoption applies to the simulator; physical route and
   configuration acceptance remain pending.
4. Implement a simulation session: Space goes HOME when initialization or a
   stopped episode requires it; at READY, Space starts leading and recording;
   during recording, Space stops following/recording and holds the attained
   posture. The next Space returns HOME without recording. `a` discards the
   current/latest episode without movement; Ctrl+C stops and cleans up.
   Keep discarded data recoverable with explicit status rather than deleting it.
5. Supply an explicit synthetic target source in the simulation subpackage,
   instead of modifying GELLO. Use synthetic cameras. Hand-E control is bypassed:
   preserve missing gripper values, never invent a URCap or grasp measurement.
   The real Hand-E integration remains the URCap server-client adapter.
6. Record intent, successfully sent targets, simulator feedback, authority and
   episode outcomes with explicit simulated provenance. Reuse the existing
   MCAP writer and boundary semantics; never relabel simulation as hardware.

## Physical-control exclusion

The new command has no arbitrary `--host` or production station-file option.
Only the named Docker simulator endpoint is supported. The launcher verifies
the pinned URSim image/service, starts a client on an internal control network
with no external route, and shares an exclusive controller lock. URSim retains
a separate loopback-published UI network. Verify simulator serial/version before
creating any control interface (its constructor can upload URScript). No lab
SSH, real URCap command, physical power/brake, gripper SET or recovery is allowed.

Application checks alone do not authenticate a remote robot. The local Docker
network boundary and verified container identity are required for this increment.
Reject a second controller before opening its control connection. No other module
may instantiate the control transport independently in a collection session.

## Design and implementation order

- Keep pure state/bounds logic independent of SDK imports and wall-clock sleeps.
  Separate simulator transport, control owner, session orchestration and tests.
- Begin with finite six-joint vectors in radians and explicit branch preservation.
  Validate routes before their first motion. Do not wrap or silently clamp input.
- Use asynchronous joint moves for HOME/routes and paced joint servo updates
  for following. Take speed/acceleration limits seriously: `servoJ`'s speed and
  acceleration arguments are unused by the SDK and are not enforcement.
- Kick the controller watchdog only from the active control loop. Keep recording
  and finalization off that loop. A failed recorder revokes following and fails
  the episode; a stalled process must still be stopped by the controller.
- Record source intent, command send success and actual readback separately.
  Preserve host receipt and controller uptime; no claim of an atomic multi-getter
  sample or physical capture synchronization.
- Add meaningful regression tests and simulator gates before reporting acceptance.
  Retain failed runs. Simulation defaults are not hardware motion limits.

## Acceptance matrix

| Case | Gate | Environment |
| --- | --- | --- |
| M03-A01.sim | Actual six-joint feedback, modes and timestamps progress throughout motion | URSim |
| M03-A02.sim | Stop during motion, settle within 1 s; joint speed <0.01 rad/s and drift <0.01 rad over the following 1 s | URSim; measured time |
| M03-A03.sim | Kill/stall control client during motion; controller stops within 1 s and does not resume on restart | URSim; independent observer |
| M05-A01/A03 | Hand-E control bypassed; absent observations remain absent | NOT RUN for physical control; missing-value software check |
| M06-A01.sim | Second owner and unauthorized source fail before command transmission | Unit tests and two clients |
| M06-A02.sim | Multi-joint trajectories and HOME return reach <0.01 rad joint error; no target-branch wrapping | URSim; UR-only |
| M06-A03.sim | Bounds, excessive step/velocity/acceleration, NaN, stale/reordered input and actual-state violation fail closed | Unit tests; representative URSim faults |
| M06-A04.sim | Invalid start/route sends no movement; fault recovery requires an explicit new session | Unit tests and URSim |
| M09-A01/A02.sim | Space boundaries stop leading/recording together, hold, then explicitly return HOME | Simulation session |
| M09-A03/A04.sim | Repeated episodes, discard, Ctrl+C and recorder fault retain honest status; no automatic restart | Software and simulation session |
| M10-A01..A03.sim | Intent/command/actual state and model provenance survive independent MCAP reading | Software and simulation episode |

Complex poses must include asymmetric six-joint changes, base/wrist angle-branch
excursions, approach to configured bounds, direction reversals, multi-waypoint
HOME returns and stop requests during motion. Cartesian singularity or collision
avoidance is not inferred from joint-limit compliance. URSim may reject a motion
through its native safety logic; report the observed rejection without weakening
application gates to manufacture a pass.

Streaming initially targets 50 Hz on Mac emulation. A 5 Hz controller watchdog,
250 ms input/feedback freshness bound, and 1 s stopping gate are simulator
acceptance settings, not promises of production real-time performance. Measure
tracking error and timing before increasing rates or adopting hardware limits.

## Sources

- [ur_rtde 1.6.5 API](https://sdurobotics.gitlab.io/ur_rtde/pages/reference/api.html):
  async moves, servoJ, stop calls and watchdog APIs.
- [UR RTDE watchdog](https://www.universal-robots.com/manuals/EN/HTML/SW5_19/Content/prod-scriptmanual/G5/rtde_set_watchdog_variable_name.htm):
  controller-side missing-update behavior; watchdogs are removed on program stop.

## Results

The shared `control/` layer and isolated `simulation/` connection factory are
implemented. `open_backend("hardware")` fails before connection. The simulator
launcher checks the exact Docker image, Compose service, internal network,
resolved peer, serial, software version and exclusive lock. The client has no
external route or mounted physical station configuration. Synthetic leader
inputs live only in `simulation/targets.py`; the controller checks the selected
source identity before accepting engagement or further targets.

The source is mounted read-only into the existing pinned-dependency runtime for
these checks; no new release image or lab deployment is claimed. SDK objects are
created only after simulator authorization. All measurements below are Mac
Docker emulation results, not physical safety acceptance.

| Case | Actual result on 2026-09-10 |
| --- | --- |
| M03-A01.sim | PASS: progressing controller uptime, joint positions, velocities and modes across the motion suite |
| M03-A02.sim | PASS: move stop 0.617 s, servo stop 0.178 s; speed below 0.01 rad/s and zero observed drift during the following 1 s |
| M03-A03.sim | PASS: independent observer measured SIGKILL stop at 0.470 s and SIGSTOP stop at 0.463 s; no resumed motion, zero observed hold drift |
| M06-A01.sim | PASS: a second client fails at the shared lease; unit tests reject an unselected source before movement transmission |
| M06-A02.sim | PASS for UR-only: asymmetric six-joint poses, base/wrist branches beyond +/-pi, targets near configured bounds, reversals and return HOME; each endpoint error below 0.01 rad |
| M06-A03.sim | PASS for implemented bounds/freshness/sequence checks in unit tests; native C403 and C207 faults revoke control and block reconnect without explicit recovery |
| M06-A04.sim | PASS for route/start rejection in unit tests and fault latch/reconnect rejection in URSim; collection gating remains M09 work |
| M05-A01/A03 | NOT RUN: Hand-E is bypassed; no physical or fabricated gripper observations |
| M09-A01..A04.sim | NOT RUN: keyboard lifecycle, recording-worker integration, discard and recorder-failure gates remain to be implemented |
| M10-A01..A03.sim | NOT RUN for moving sessions: control/authority records and URSim provenance still need MCAP integration |

The final motion repeat after source-selection validation also passed: move
stop 0.622 s, servo stop 0.182 s, zero observed hold drift, and READY peak
0.3 rad/s. URSim was left stopped at HOME after that run.

The trajectory suite preserved angle branches and exercised base -5.3 rad and
wrist 3 +/-5.2 rad. READY peaked at the configured 0.3 rad/s. A 12 s asymmetric
50 Hz synthetic stream had a maximum contemporaneous target/readback difference
of 0.0466 rad; the final regression run measured 0.0684 rad while container
software tests also ran. This lag measurement is not a tracking-accuracy acceptance or a
hardware real-time guarantee; only endpoint arrival currently has a 0.01 rad gate.

Retained findings and failed runs:

- The first factory probe rejected Local mode before creating the SDK controller.
- A route toward `[4, -2, -0.9, -3.8, 1.8, 4.1]` rad triggered native C403
  clamping protection. The application faulted and did not recover automatically.
  Subsequent branch/limit tests use a different wrist-1 route; no limit or stop
  gate was weakened. Collision avoidance is still not implemented.
- Killed/stalled RTDE input triggered native C207 protective stop. The first
  watchdog harness incorrectly expected a normal reconnect and failed. The
  corrected harness accepts the observed protective latch only after proving
  timely stop and stable hold, and requires reconnect rejection. Protective
  stop release was a separate, explicitly invoked simulator recovery between
  tests; it is not an application retry or automatic recovery path.

Local evidence is retained under `artifacts/simulator-control/`, including
`motion-1789021178178614212.json`, final repeat
`motion-1789021687104549128.json`, `watchdog-1789021406854411138.json`,
`watchdog-1789021499933815583.json` and the earlier failed reports. Durable
conclusions above do not depend on retaining that ignored directory.

Software regression: native Python 3.12, 156 passed / 4 skipped; dependency
container, 156 passed / 4 skipped before sourcing Jazzy. The two container
checks are opt-in; the two ROS compatibility checks need the Jazzy environment.
Black passed and Pylint exited successfully at 10.00/10. After explicitly
sourcing `/opt/ros/jazzy/setup.bash`, both ROS compatibility tests passed
(2 passed). The optional host container checks were not rerun for this source-only
control increment.

Physical M03/M05/M06/M09 acceptance remains NOT RUN. GELLO hardware integration,
native Home watchdog handover, moving-session MCAP integration and M09 lifecycle
are still outstanding; this cross-module plan remains implementing.

## READY and architecture decision

The official [PolyScope Home node](https://www.universal-robots.com/manuals/EN/HTML/SW5_21/Content/prod-usr-man/software/PolyScope/content/AdvProgNodes/home_en.htm)
uses installation-defined joint angles. A documented direct Dashboard `go home`
API was not found; the built-in URCap HomeNode is a program-construction API.
The user confirmed that the physical installation Home can be configured to READY.
A dedicated one-shot `READY.urp` containing the native Home node is therefore an
approved candidate, invoked through Dashboard `load`/`play`. Verify its explicit
joint speed/acceleration, completion readback, stop behavior and watchdog/ownership
handover in URSim before adopting it. There is no claim that a plain Dashboard
connection stops a program on disconnection. The shared bounded `moveJ` path
remains available for trajectories and control tests; native Home integration
must preserve the same application-facing READY target and arrival check. Initial READY limits are 0.3 rad/s
and 0.5 rad/s²; general simulator test moves have separate limits. These values
are recorded in the simulator profile, not accepted as physical safety settings.

Keep shared motion types, bounds, SDK adapter and state machine under `control/`.
Keep endpoint authorization, synthetic target generation and local integration
fixtures under `simulation/`. A physical backend factory raises before connection;
future physical authorization can reuse the same control implementation. Do not
scatter `if simulated` branches throughout control logic. The independent physical
read-only path stays available and unchanged.


## Native PolyScope Home verification

The user confirmed that the physical installation Home can be configured to the
required READY pose. The official Home node exposes joint speed and acceleration.
Dashboard provides `load <program.urp>`, `play`, and `stop`; there is no documented
direct `go home` command in the referenced interface.

In URSim, the installation Home was set to the measured
`[0, -90, -90, -90, 90, 0]` degree pose. A non-looping `ready.urp` with one Home
node was saved with joint speed 15 deg/s and acceleration 25 deg/s². Its generated
URScript contains the matching native `movej`, `v=0.2617993877991494 rad/s` and
`a=0.4363323129985824 rad/s²`. These are probe settings, separate from the shared
SDK READY defaults of 0.3 rad/s and 0.5 rad/s².

`tests/simulation/native_home.py` runs SDK offset positioning, closes that control
program, and then invokes the native program through Dashboard. It passed two
completed returns and one interrupted return. Peak measured native Home speed
was 0.2618 rad/s; interrupted stop took 0.193 s, held its attained position, and
did not continue HOME. The generated script and test report are retained as
`native-home.script` and `native-home-1789021305861908924.json` in local artifacts.

Closing the Dashboard connection does **not** stop the native program: both
completed returns ran after their command sockets closed. A plain Home program
was therefore callable; the initial proposal required a controller-side
heartbeat before default adoption. The later user decision below supersedes that
heartbeat proposal. Exclusive handover and measured stop/arrival remain required.

The physical READY program must retain the intended station installation,
including its Hand-E URCap/tool configuration. The simulator's default
installation must never be copied to the physical arm. No physical access or
control was performed for these tests.

Sources:

- [UR Home node](https://www.universal-robots.com/manuals/EN/HTML/SW5_21/Content/prod-usr-man/software/PolyScope/content/AdvProgNodes/home_en.htm).
- [UR Dashboard interface](https://www.universal-robots.com/manuals/EN/HTML/SW5_23/Content/prod-dashboard/Dashboard_table.htm).
- [UR C403 clamping protection](https://www.universal-robots.com/manuals/EN/HTML/SW10_10/Content/prod-err-codes/topics/CODE_403.html).


## Autonomous sprint alignment: native READY (2026-09-10)

The user now selects native Dashboard/Home stability and default Home node speed
and acceleration. The prior proposed native-HOME heartbeat requirement is
superseded: native HOME may complete after its host disconnects. Controller-side
watchdog requirements apply to SDK/teleoperation control and episode handover.
Physical control remains prohibited. See the [sprint](../m13-acceptance/simulator-sprint.md).

Implement a reusable native-program transport alongside the SDK transport, with
one owner and one current mode. Close/revoke the SDK program before loading Home;
reacquire the SDK only after measured Home completion or an explicit stopped
handover. Preserve actual runtime state, allow normal one-shot Home completion,
and never infer arrival from a successful `play`. Validate the expected Home
joint configuration before launch. Keep native program defaults independent of
streaming target speed limits; this is an explicit user-approved distinction.

Acceptance: native-default speed/acceleration preserved, return from asymmetric
poses, stop midway and hold, host disconnect permits Home completion, later SDK
handover succeeds without resuming old targets, and malformed/unexpected program
or configuration blocks motion. Tests use only the isolated URSim endpoint.


## Native HOME integration results (2026-09-10)

Implemented reusable `NativeHome` beside `URTransport`, sharing one persistent
RTDE receiver. The simulator station permits exactly one program owner. It
requires measured standstill and a stopped native program before SDK acquisition;
SDK teardown completes before native load/play. Native completion requires actual
joint arrival, standstill and stopped runtime, never just a Dashboard reply.

A single Home node at the start of a program failed Dashboard play from the
asymmetric test pose because PolyScope requested AutoMove. The earlier base-only
probe had not exposed this. The prepared fixture now uses UR's documented
[current-pose variable waypoint before the Home node](https://www.universal-robots.com/articles/ur/programming/creating-a-safe-home-routine/).
This zero-displacement preamble avoids AutoMove; the actual return remains the
native Home node. Preparation checks the installed Home and original one-node
program, preserves the installation and records both file hashes. No compiled
`.script` fixture is required. Earlier failed reports remain retained.

- M03/M06 software and actual URSim native-HOME checks: PASS. Eight dedicated
  native-program unit cases cover rejected starts, stale feedback, premature
  program completion, ownership and interrupted hold.
- `python scripts/sim_control.py home`: PASS, repeated after removing the
  diagnostic compiled script and after adding the measured SDK handover guard.
  Latest report: `home-defaults-1789023918694649009.json` in local simulator
  artifacts. Default peak joint speed was 1.047198 rad/s (60 deg/s), with the
  configured 1.396263 rad/s² acceleration (80 deg/s²).
- Asymmetric return, midpoint stop and one-second position hold: PASS; latest
  stop took 0.288 s. SDK reacquisition did not resume old targets.
- Immediate native client process exit: PASS; HOME finished normally without a
  host heartbeat, as explicitly selected by the user.
- Physical native program, tool/installation preservation and collision route:
  NOT RUN. Simulator results do not establish a safe physical path.

The host launcher is `python scripts/sim_control.py home`; `prepare-home` only
prepares the verified simulator fixture. Physical program deployment is absent.
