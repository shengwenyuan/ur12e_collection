# M01–M13 Simulator Handoff

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Updated: 2026-09-10. This matrix distinguishes implemented software from physical
acceptance. No lab SSH, physical robot, gripper or camera connection occurred in
this autonomous sprint. No GUI automation was required.

| Module | Implemented behavior | Current evidence | Remaining boundary |
| --- | --- | --- | --- |
| M01 | Ubuntu 24.04/Jazzy runtime/dev images, pinned dependencies, non-root mounts, offline delivery | Source-matched amd64 images; installed-package and mount checks PASS | Current image deployed to lab PC with software gates PASS (2026-09-11); new physical checks NOT RUN |
| M02 | Strict station config, serialized atomic updates, explicit setup/mount declarations and calibration activation | Configuration, concurrent updates, failed replacement and identity tests PASS | Physical identities/setup and production motion configuration require lab verification |
| M03 | Output-only UR readback; shared UR transport behind verified simulator-only connection | Actual URSim control gates PASS; powered physical Manual/Local short readback PASS (2026-09-11) | Physical control factory remains disabled |
| M04 | Explicit unavailable GELLO API; isolated test waveform | Missing state and rejected physical requests PASS | Real DYNAMIXEL transport, mapping, torque/holding and load tests remain externally blocked |
| M05 | GET-only Robotiq URCap reader with raw registers and bounded polling | Raw values, malformed/stale replies and bypass provenance PASS | Real Hand-E actuation/grip retention NOT RUN; simulator values remain null |
| M06 | Exclusive native Home/SDK ownership, branch-preserving limits, freshness, stop and fault latch | Complex/asymmetric/near-limit URSim routes, native Home defaults and client-loss behavior PASS | Physical routes/cable clearance and coordinated GELLO READY/HOLD NOT RUN |
| M07 | Persistent three-camera rig, RGB-D alignment boundary, source health; optional parent-owned shared slots for simulator | Earlier physical camera acceptance retained; new simulator slot/restart tests PASS | New release camera smoke and semantic left/right binding remain lab work |
| M08 | Wrist-anchored real-frame matching, 16.7 ms skew, 75 ms wait/drain, no reuse | Deterministic/failure tests and earlier physical grouping gates PASS | Physical clock accuracy/exposure synchronization is not established by SDK global time |
| M09 | Space HOME/start/stop, held review, a discard, Ctrl+C, recorder supervision and explicit authority handover | Short/40-second URSim sessions and discard/recorder-kill/restart/SIGINT PASS | 20 x 40 controlled batch and independent audit PASS; physical GELLO/Hand-E coordination NOT RUN |
| M10 | Separate intent/sent/actual streams, authority interval, exact clocks, immutable calibration context and optional read-only ROS observer | MCAP source/coverage/pairing and current-verifier readback PASS | Real GELLO mapping, calibrated TF and calibration services remain pending |
| M11 | Independent H.264 streams, exact uint16 PNG, verified atomic MCAP; optional official LeRobot v3 RGB/arm export | Codec/corruption/failure gates PASS; actual official loader verifies 1,291 frames in two episodes | Full simulator duration gate PASS; gripper/depth training projection and physical task-image export quality NOT RUN |
| M12 | ChArUco detection, fixed/wrist geometry, independent held-out checks, stationary checkpoint gate, offline solve/verify/setup/activate | 30 offline tests across geometry, real rendered PNG pixels, immutable evidence and failure-preserving activation PASS | Taught physical script/checkpoint transport, TCP-to-flange offset, board dimensions/visibility and real accuracy thresholds NOT RUN |
| M13 | Hardware-free shadow, actual URSim functional/fault batches, independent final audit and reproducible reports | Software/native ROS/installed-image checks PASS | Twenty 40-second episodes, independent audit and final-image fault regression PASS; new lab deployment NOT RUN |

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

ROS 2 Jazzy and native ROS-CDR/rosbag2 interoperability are tested. Optional
`--ros-observe` publishes separate actual/intent/sent JointState streams, TCP
PoseStamped, original M10 records and retained phase/context. Seven real Jazzy
tests and actual URSim observer-kill isolation pass. It is a bounded read-only
process; main collection is independent of its delivery. Joint/pose publication
covers recorded windows only. Calibration services and TF remain unimplemented;
no unverified TCP-to-flange transform is broadcast.

## Evidence and follow-up

- Functional commits: `429b701`, `9ad0137`, `535fe69`, `60bf3da`, `4bb00e1`,
  `36c00b2`, `57f152c`. Their module plans retain actual checks and limitations.
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


Final source-matched runtime: `ur12e-collection:sim-runtime-6e48d82`.
Image ID: `sha256:3165576f143dede3da111e790e0ade4dcb262d7bac07ebb8cd8e940521e62556`.
Native regression is 248 PASS / 5 environment skips; installed Jazzy is
251 PASS / 2 host-only skips, and both mount tests separately PASS. The runtime
contains 59 hash-matched Python/schema files. Final-image active discard,
recorder-kill/restart and Ctrl+C/hold regression also PASS. Source and deployment
instructions are in the M01 plan; physical control remains disabled.

## Current image consolidation (2026-09-11)

The daily collector image is now `ur12e-collection:current`, shared by dev,
station, camera and URSim-client launchers. It uses the tested runtime plus test
tools; official URSim remains separate. Current image ID:
`sha256:a3d22d1ffa6c36331116a4c870f7bb841d84ec036cd9a2d23460345ce15bab96`,
source `bbc56a8c714e7a8bc1b6f9124af80339352a2b97`. A discovered cancellation
race was corrected without changing control or capture semantics. Native checks
pass 252 cases; installed Jazzy checks pass 255 cases, and the two host mount
checks pass separately. No motion or physical device tests were run for image
consolidation. Earlier motion/camera evidence retains its original image identity.
See M01 `image-consolidation.md` for bundle selection and pending cleanup.


The consolidated image is now deployed on `ssh ur12e-collection`; native Ubuntu
255 installed tests, both host mount tests, all 59 source hashes and unchanged
production config PASS. No cameras, Hand-E or UR controller were accessed.
See `lab-20260911.md` for deployment. A subsequent user-authorized powered
Manual/Local read-only check passed; see M03 `live-state-20260911.md`. Physical
control remains prohibited and motion gates remain open.
