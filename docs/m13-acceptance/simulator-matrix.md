# M01–M13 Simulator Handoff

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Updated: 2026-09-10. This matrix distinguishes implemented software from physical
acceptance. No lab SSH, physical robot, gripper or camera connection occurred in
this autonomous sprint. No GUI automation was required.

| Module | Implemented behavior | Current evidence | Remaining boundary |
| --- | --- | --- | --- |
| M01 | Ubuntu 24.04/Jazzy runtime/dev images, pinned dependencies, non-root mounts, offline delivery | Source-matched amd64 images; installed-package and mount checks PASS | Updated image deployment on the lab PC NOT RUN |
| M02 | Strict station config, serialized atomic updates, explicit setup/mount declarations and calibration activation | Configuration, concurrent updates, failed replacement and identity tests PASS | Physical identities/setup and production motion configuration require lab verification |
| M03 | Output-only UR readback; shared UR transport behind verified simulator-only connection | Actual URSim feedback, stop/hold, killed/stalled client watchdog PASS | Physical control factory remains disabled |
| M04 | Explicit unavailable GELLO API; isolated test waveform | Missing state and rejected physical requests PASS | Real DYNAMIXEL transport, mapping, torque/holding and load tests remain externally blocked |
| M05 | GET-only Robotiq URCap reader with raw registers and bounded polling | Raw values, malformed/stale replies and bypass provenance PASS | Real Hand-E actuation/grip retention NOT RUN; simulator values remain null |
| M06 | Exclusive native Home/SDK ownership, branch-preserving limits, freshness, stop and fault latch | Complex/asymmetric/near-limit URSim routes, native Home defaults and client-loss behavior PASS | Physical routes/cable clearance and coordinated GELLO READY/HOLD NOT RUN |
| M07 | Persistent three-camera rig, RGB-D alignment boundary, source health; optional parent-owned shared slots for simulator | Earlier physical camera acceptance retained; new simulator slot/restart tests PASS | New release camera smoke and semantic left/right binding remain lab work |
| M08 | Wrist-anchored real-frame matching, 16.7 ms skew, 75 ms wait/drain, no reuse | Deterministic/failure tests and earlier physical grouping gates PASS | Physical clock accuracy/exposure synchronization is not established by SDK global time |
| M09 | Space HOME/start/stop, held review, a discard, Ctrl+C, recorder supervision and explicit authority handover | Short/40-second URSim sessions and discard/recorder-kill/restart/SIGINT PASS | 20 x 40 controlled batch and independent audit PASS; physical GELLO/Hand-E coordination NOT RUN |
| M10 | Separate intent/sent/actual streams, authority interval, exact clocks, missing gripper and immutable calibration context | MCAP source/coverage/pairing and current-verifier readback PASS | Real GELLO mapping and live typed ROS graph interfaces remain pending |
| M11 | Independent H.264 streams, exact uint16 PNG, verified atomic MCAP; optional official LeRobot v3 RGB/arm export | Codec/corruption/failure gates PASS; actual official loader verifies 1,291 frames in two episodes | Full simulator duration gate PASS; gripper/depth training projection and physical task-image export quality NOT RUN |
| M12 | ChArUco detection, fixed/wrist geometry, independent held-out checks, stationary checkpoint gate, offline solve/verify/setup/activate | 30 offline tests across geometry, real rendered PNG pixels, immutable evidence and failure-preserving activation PASS | Taught physical script/checkpoint transport, TCP-to-flange offset, board dimensions/visibility and real accuracy thresholds NOT RUN |
| M13 | Hardware-free shadow, actual URSim functional/fault batches, independent final audit and reproducible reports | Software/native ROS/installed-image checks PASS | Twenty 40-second episodes and independent audit PASS; final image/bundle handoff in progress |

## Current architecture and operator behavior

The application has one READY/HOME target: `[0, -90, -90, -90, 90, 0]` degrees.
There is no separate all-zero startup motion. Native Home uses its installed
60 deg/s and 80 deg/s² defaults. Its controller-owned motion may finish after a
client disappears; SDK following retains a 5 Hz controller watchdog. Programs
cannot overlap ownership, and actual stopped arrival is required for handover.

Space advances only the current allowed phase: HOME, start, stop/hold, then HOME.
Held-key repeats cannot cross phases. `a` discards the current/latest episode;
verified files remain with an explicit outcome marker. Ctrl+C stops and preserves
unfinished data without asking for HOME or releasing a gripper. A normal stop
leaves task success unknown. The test leader is explicitly under `simulation/`.

The simulator profile uses three camera processes, eight shared slots per role,
one matching/recording process with a writer thread, and one independent final-file
verifier. Only frame headers cross camera IPC. The control process never waits for
encoding or storage. The explicit simulator queues hold 16 image triples and 128
small control records. Active recorder supervision is 500 ms; a 3 s allowance
exists only after confirmed stop while the SDK releases ownership. This is not
a relaxed active-control deadline. Physical/shadow defaults remain unchanged.

ROS 2 Jazzy and native ROS-CDR/rosbag2 interoperability are tested. Live typed
status publishers, calibration services and TF broadcasting are not implemented.
They remain observability work; the current CLI/session/MCAP logic does not depend
on them. In particular, no unverified TCP-to-flange transform is broadcast.

## Evidence and follow-up

- Functional commits: `429b701`, `9ad0137`, `535fe69`, `60bf3da`, `4bb00e1`,
  `36c00b2`. Their module plans retain actual checks and limitations.
- Native Home and complex-motion evidence: M06 `simulator-control.md`.
- Latest physical camera layout acceptance predates this sprint; see
  `layout-recheck-20260910.md`. It is not a new physical test of this image.
- M11 optional export and M12 offline usage have separate reproducible instructions.
- Failed long batches remain under ignored `artifacts/simulator-control/`. They
  never count toward a successful 20-episode batch. The latest run is frozen and
  independent of ongoing documentation/test edits.

When the user returns, prioritize lab read-only image/camera smoke, physical
left/right labels and controller installation/Home review. Physical control needs
new explicit authorization, site bounds/clearance and validated Hand-E/GELLO
interfaces. No such authorization is inferred from simulator success.


Full controlled batch: **20 x 40 s PASS**, including current independent file and
quality audit. Accepted 23,998 / 24,007 decisions (99.9625%), worst 99.75%, at most
two consecutive rejections, zero native source gaps/repeats. The last complete
episode is explicitly discarded for lifecycle validation. See the M13 plan for
resource limits and synthetic-versus-physical interpretation.
