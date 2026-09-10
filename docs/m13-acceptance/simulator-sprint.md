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

- Baseline: 156 native tests pass, four environment/opt-in tests skipped; two
  additional Jazzy compatibility cases passed in the dependency container.
  Black/Pylint passed. Committed as `429b701`.
- Native Home: default parameters, asymmetric return, stop/hold, client loss and
  exclusive SDK handover pass actual URSim tests; see M06 simulator-control.md.
- Next: persistent moving session and independent recording/provenance.
- M09/M10/M11: short moving episodes and actual URSim discard/recorder-loss/SIGINT
  gates pass; the 20 x 40-second batch is being diagnosed (not accepted). Changes
  are uncommitted until the coherent session increment passes its recorded gates.
- M12: offline geometry, ChArUco detection and pure stationary checkpoints pass
  19 software tests. Result persistence/activation remains the next M12 increment.
- Subsequent work: configuration/device audit, LeRobot export and release remain
  pending. Preserve the earlier physical acceptance boundaries.
