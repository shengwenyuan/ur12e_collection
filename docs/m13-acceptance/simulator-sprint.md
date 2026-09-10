# M01–M13: Autonomous Simulator Acceptance Sprint

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned / implementing, 2026-09-10.

The user authorized autonomous development, simulation tests and incremental
commits over their next 6–8 hours away. Write concrete plans before each durable
increment, make routine choices independently, and record unresolved details
without waiting for replies. This explicit delegation supersedes repeated
alignment pauses for this sprint. Preserve the established module/acceptance IDs.
The existing simulator-control plan remains the detailed control/session plan.

## Boundaries and accepted change

Only the local, identity-verified official URSim may receive motion commands.
No lab SSH, physical robot, gripper or camera access. GUI automation, if needed,
may operate Docker Desktop only; do not operate the browser or other apps.
Use terminal, Docker CLI and program/configuration files for simulator work.
GELLO hardware remains external and unavailable; Hand-E may be explicitly bypassed.
Keep synthetic sources in simulation/tests, never as silent physical fallbacks.

READY uses a dedicated PolyScope Home program through Dashboard, retaining native
Home defaults (the installed 5.22.2 node defaults are 60 deg/s and 80 deg/s²).
Do not impose a host heartbeat during that native program: on client loss it may
finish the bounded, controller-owned Home motion. Teleoperation still requires
its controller watchdog, explicit ownership, source freshness and episode
handover. A completed Dashboard `play` reply is not an arrival observation.
No automatic restart of following or episode recording is permitted.

## Ordered increments

1. Commit the existing reviewed read-only recording and URSim/control baseline
   after current regression checks, preserving partial-module status.
2. M03/M06: integrate native Home, explicit native-program/SDK handover, measured
   arrival, default motion parameters, stop, rejection and restart tests.
3. M09/M10/M11: a persistent simulation session with Space start/stop/READY,
   debounced input, recoverable discard, Ctrl+C, bounded independent recording,
   authority/intent/sent/actual provenance, and no invented gripper values.
4. M02/M04/M05: audit configuration readiness and unavailable-device contracts;
   add only useful explicit interfaces. Physical communication/control acceptance
   remains blocked by hardware, not satisfied by a fake implementation.
5. M11: offline MCAP-to-LeRobot v3 export using the pinned official package,
   truthful timestamp association, explicit missing-gripper policy and immutable
   output. Verify with its real loader. If an unresolved training projection
   cannot be chosen honestly, implement validation/planning and record it.
6. M12/M02/M10: independent offline board detection and two-round geometry
   solving, observability and held-out checks, stationary checkpoint capture
   contracts and atomic calibration activation. Use configurable board/poses;
   do not invent physical calibration or claim synthetic accuracy is lab accuracy.
7. M01/M07/M08/M13: repeat affected integration/failure tests, long simulation
   sessions (target 20 x 40 s), build and verify a source-matched amd64 image,
   package reproducible local delivery, and publish a concise module matrix.

Each increment updates its owning English document with actual PASS/FAIL/NOT RUN
results and commits only coherent tested work. Keep failed artifacts and unresolved
questions. Avoid broad speculative frameworks and duplicate simulator/physical
control implementations. No cloud push or lab deployment is authorized here.

## Acceptance and handoff

Preserve existing camera acceptance. New simulator acceptance must distinguish
pure unit tests, actual URSim motion, synthetic-camera MCAP tests, ROS/LeRobot
loader tests and physical gates. Validate stop/hold, exclusive ownership, late or
failed recorders, failure retention, no unintended motion and source provenance.
Record exact commands, source/image identities and relevant timing/resource limits.

A module is not fully accepted when its required physical evidence is missing.
The handoff matrix lists implemented logic, simulation evidence, remaining hardware
checks and unresolved decisions for each M01–M13 module. Keep this file current so
a scheduled continuation can resume the next useful increment without duplicating
work or changing previously accepted behavior.

## Progress

- Baseline `429b701`; native Home `9ad0137`; offline geometry `535fe69`;
  controlled session/export `60bf3da`; calibration activation `4bb00e1`;
  coverage/budget correction `36c00b2`.
- Full controlled batch `session-1789028767567594961`: **20 x 40 s PASS**.
  Current independent audit also PASS: 23,998 / 24,007 accepted (99.9625%),
  worst 99.75%, maximum two consecutive rejections, no native source gaps/repeats.
  Final episode is intentionally discarded as an outcome test. Preserve failed
  predecessors; they never count toward this successful batch.
- Real terminal group Ctrl+C exposed child interrupts; child-only SIGINT ignoring
  plus parent-owned abort fixes cleanup. Group/TTY tests pass, active data remains
  partial, and independent URSim readback shows stopped runtime, zero speed/drift.
- Latest Mac suite: **242 PASS / 4 skipped**, Black/Pylint 10.00/10. A prior
  source-matched runtime/dev pair for `36c00b2` passes 234 installed Jazzy tests
  and two separate mount tests. New interrupt changes need the final image rebuild.
- Official LeRobot 0.6.1 writer/loader: 1,291 frames / two episodes PASS, exact
  numeric values and sampled RGB MAE below 0.719/255. M12 has 30 offline tests,
  including rendered PNG detection, independent geometry and atomic activation.
- Next bounded increment: optional read-only ROS observation sidecar, as planned
  in `docs/m10-data-contract/ros-observation.md`. No control input or camera
  duplication. Test real Jazzy round trips and observer-loss isolation in URSim.
- Then refresh final runtime/dev images, package the offline release, update
  `simulator-matrix.md`, and close the scheduled continuation. No lab/physical
  connection or non-Docker GUI control is permitted.
