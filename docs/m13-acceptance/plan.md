# M13: Camera-Only Collection Batch

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Status: implemented / physical acceptance pending
- Alignment: on 2026-09-09 the user approved snapshot -> persistent M07 -> M13
  shadow -> M09 lifecycle development and local deployment/testing, targeting
  a complete batch for the next lab session.
- Dependencies: M02/M10 snapshot, M07 source, M08 matcher, M11 writer.

## Scope and interfaces

Provide `ur-collect shadow --backend hardware|synthetic --output DIR` with
explicit hardware station input, task/revision provenance, and bounded episode
count/duration. Defaults are 20 episodes of 40 seconds. Hardware starts only
three configured RealSense pipelines; no robot adapter or motion entrypoint is
involved. Synthetic data is explicitly labeled and uses synthetic station facts.

Build a versioned snapshot from validated station configuration and observed
camera facts. Require identity/model agreement, image profile, depth scale and
intrinsics, and explicit clock evidence. Preserve null calibration; do not invent
extrinsics. Store and validate this snapshot in every episode.

Keep one spawned camera process per role alive across all episodes, with bounded
frame queues, full alignment warm-up, explicit readiness and worker failure
reporting. SDK global-time domains are required on hardware; preserve original
source/receipt times. Common SDK clock availability is not physical exposure
synchronization or independently measured clock accuracy. Report that validation
as pending. Missing frames, source faults, IPC overflow, and dead workers fail the
batch explicitly; no automatic reconnect/resume.

M09 owns a reusable camera-episode lifecycle: start, submit, stop/finalize, poll,
abort. Continue draining cameras while finalization independently decodes MCAP;
do not restart cameras or build a backlog between episodes. Frames received
before a new episode boundary cannot enter it. Keyboard leading, READY moves,
and robot stop/hold remain pending M06 integration.

## Implementation and validation

1. Version snapshot schema and builder under M10, reusing M02 station validation.
2. Implement the persistent M07 rig with bounded startup/read/cleanup and explicit
   synthetic source for software integration.
3. Add M09 lifecycle and M13 timed shadow entrypoint, per-episode verification,
   failure reports, acquisition/matching/encoding/queue/storage statistics.
4. Test identity/snapshot mismatches, timing faults, stalled/dead workers,
   asynchronous finalization, overflow, interrupt, multiple episodes and cleanup.
5. Build/test local Jazzy images and prepare explicit amd64 lab commands. No SSH
   is assumed available; deployment to the lab remains a next-session action.

Acceptance IDs: M07-A01/A02/A03 persistent identity/profile/time; M10-A03 snapshot
traceability; M09-A04 truthful completion/failure; M13 camera path and M11-A04
codec/storage verification. Software tests must pass; hardware 20 x 40 seconds,
clock accuracy, actual playback and scene quality remain NOT RUN until measured.
Do not claim full M09 or robot acceptance from camera-only tests.

Engineering bounds: four queued frames per role, two-second read/stale timeout,
30-second startup, two-second full alignment warm-up. Monitor SDK global time
against host Unix time (two-second sanity window); stop on a host wall/monotonic
clock discrepancy above 100 ms. These detect gross faults, not synchronization
accuracy. Record all limits; refine from lab evidence.

The runtime adds ROS Jazzy rosbag2 CLI/transport/MCAP and foxglove_msgs packages
so that deployment contains the native reader and video message type support.
Record exact resolved Debian versions in the image package manifest. The SDK
clock distinction follows the pinned [librealsense frame API](https://github.com/realsenseai/librealsense/blob/v2.56.5/include/librealsense2/h/rs_frame.h);
ROS message availability follows the [Jazzy release](https://github.com/ros2-gbp/ros_foxglove_msgs-release).

## Results (2026-09-09)

| Case | Result | Evidence and limit |
| --- | --- | --- |
| M10-A03 | PASS software | Versioned snapshot builder, station reuse, identity/model checks, mutation isolation and explicit uncalibrated context |
| M07-A01/A02/A03 | PASS software; NOT RUN hardware | Three persistent spawned synthetic sources, bounded queues/readiness/cleanup, source clock and counter checks; actual SDK capture is next-session work |
| M09-A04 | PASS camera slice | Nonblocking finalization, independent episodes, old-receipt exclusion, writer/source failure propagation, real subprocess SIGINT |
| M13-A01/A02 | PASS software; NOT RUN hardware | Two 40-second synthetic episodes and twenty 2-second synthetic episodes; physical 20 x 40 remains pending |
| M09-A04 / M13-A04 | PASS software | IPC overflow, stale/dead workers, startup failure, interrupt and cleanup failures remain explicit; partial recordings never count as completed episodes |
| M11-A04 / M01-A02.1-smoke | PASS local deployment checks | Native ROS CDR including Foxglove video, rosbag2 MCAP reader, CLI info/play smoke, runtime SDK imports and mounted-output smoke |

Final native checks: Black and Pylint 10.00/10; 88 tests passed, four skipped
(two ROS-only and two opt-in Docker mount tests). Final arm64 and amd64 Jazzy
images each passed 90 tests, skipping only the two host Docker checks. The two
mount tests passed separately against the amd64 runtime. Actual SIGINT was tested
against a running subprocess and active partial file, not only a mocked callback.

The two full-duration synthetic episodes stored 1200 and 1197 accepted groups,
25,663,464 and 25,607,537 bytes. Two missing-view rejections in the second episode
remain visible. All three sources reported no color/depth counter gaps or depth
repeats across 2688 observations each, including finalization periods. These are
software-source measurements, not physical sensor or production codec budgets.
Evidence: `artifacts/offline/shadow-2x40-20260909/report.json`.
Twenty short episodes completed with 1197 accepted groups and 25,715,727 total
MCAP bytes: `artifacts/offline/shadow-20x2-20260909/report.json`.

The first mounted amd64 runtime smoke failed with camera IPC overflow during
concurrent container tests. It produced no completed episode and retained failure
and cleanup diagnostics in `shadow-runtime-smoke-20260909/report.json`. An
isolated rerun completed both episodes in `shadow-runtime-smoke-20260909-02/`.
Mac amd64 emulation is not production throughput acceptance. Queue/codec limits
were not relaxed; real Ubuntu headroom is a priority lab check.

Runtime dependencies include Python 3.12.3, pyrealsense2 2.56.5.9235, ur-rtde
1.6.5, PyAV 15.1.0, OpenCV 4.12.0.88, MCAP 1.4.0 and ROS 2 support 0.5.7.
Resolved Debian packages: foxglove_msgs 3.4.1-1noble.20260615.111611;
ros2bag 0.26.11-1noble.20260616.083858; MCAP storage
0.26.11-1noble.20260616.074830; rosbag2 transport
0.26.11-1noble.20260616.082423. Full manifests accompany the bundle.

Image source label: `15c9d26-working-shadow` (working-tree increment, not a clean
commit claim). Final image identities:

- amd64 runtime `ur12e-collection:shadow-runtime`:
  `sha256:8c393dd43cb8aaec6986489c0990a48aaf3f4eed43673b549b869de67563cbd2`.
- amd64 test image `ur12e-collection:shadow-amd64-dev`:
  `sha256:a6f17c25bd20aced77bc6cf93e1980c93aac580ef356c9def189355e8d8a2d0f`.
- arm64 test image `ur12e-collection:shadow-arm64-dev`:
  `sha256:81bdb3eff25f61313ad921989c341339fbcb630be877418a45631ff5e8ba5188`.

No SSH, lab deployment or robot motion occurred. Physical 20 x 40 acceptance,
clock accuracy, Foxglove visual quality, live SDK cleanup and actual USB throughput
remain NOT RUN. M09 keyboard leading/READY/hold, calibration execution, LeRobot
export and control-rate load remain outside this camera batch.

Final offline delivery: `artifacts/releases/ur12e-shadow-bundle-20260909-v2/`.
All delivered file checksums passed an independent Python 3.12 verification.
`image.tar` is 474,395,648 bytes, SHA-256
`75090bc74e191508eb15bd656fe806cc6cd526ef9564259ad4267f216a23ca75`.
The bundle includes image and package manifests, immutable-image launchers,
read-only station mounting, the camera shadow command, and LAB-RUNBOOK.md. V2
attempted to correct the loader hint, but the missing Compose profile was
found and corrected during the 2026-09-10 deployment; the runtime image is
unchanged. The first bundle remains a historical local artifact. Fresh loading
on the actual Ubuntu station is NOT RUN. New source changes remain in the working
tree; pre-existing M12 planning changes were preserved.


## Lab deployment update (2026-09-10)

The user authorized synchronization and checks with no cameras attached. The
new `ur12e-shadow-bundle-20260910` loaded successfully on the actual Ubuntu PC.
It reuses the above image and corrects the launcher profile/configuration paths.
All 24 synthetic episodes passed independent verification; ROS info/play,
non-root mount persistence, and active-recording SIGINT checks passed. Camera
inventory is empty and the station still needs three serial bindings.
See the [deployment acceptance record](lab-20260910.md) for measurements, exact
commands, evidence locations, and remaining physical checks. This supersedes
the previous offline-only deployment status; physical acceptance remains pending.

## Accepted software baseline (2026-09-10)

The user requested committing the passed software scope and removing repeated
software acceptance from the next physical-camera session. The [baseline record](software-baseline.md)
closes these cases and defines the remaining hardware evidence. Stable M13 IDs
retain their original meta-plan meanings: A01 no-motion shadow, A02 diagnostics,
A03 twenty full-duration episodes, A04 truthful software/hardware separation.
Duplicate, conflicting draft labels were corrected; physical A03 remains NOT RUN.

## Physical camera run (2026-09-10)

The user connected all three cameras and authorized the existing pipeline's
physical acceptance sequence. Use the deployed image corresponding byte-for-byte
to software baseline commit `4f046a9`. Do not repeat closed software acceptance.
Inventory/preflight: D405 and two D435IF units, all USB 3.2; each yielded 90
640x480 aligned RGB-D frames in three seconds with no color/depth counter gaps
or repeated depth and an exact depth PNG round trip. This is a preflight, not
recording-throughput acceptance. Actual third-view role confirmation is pending.
Proceed with a two-episode smoke, then 20 x 40 seconds if its timing and recording
results support continuation. Record failures before repairs; preserve partials.
Physical clock accuracy and scene quality remain open until measured/reviewed.

Physical results: the short and 40-second hardware-input recordings produced
valid MCAP files, but D405 source stability failed. The problem also reproduced
with no encoding and in the original diagnostic with D405 alone. Both D435IF
cameras passed their 20-second diagnostic. The subsequent direct-connection
comparison passed 40-second solo and three-source tests plus two 40-second
recordings with zero source gaps/repeats. Both recordings independently verified,
but accepted only 987 and 1117 groups; timing/grouping remains unresolved.
M13-A03 stays NOT RUN pending grouping diagnosis and physical role confirmation. See the
[physical test record](physical-20260910.md) for measured results and restart steps.
No source or image changes were made; original role binding remains unconfirmed.

## Timing and resource experiments (2026-09-10)

The user approved the [timing correction experiments](../m08-frame-matching/timing-diagnosis.md)
and requested final resource/gate alignment. A 75 ms wait and 1 ms polling remove
the bulk of deadline-related grouping losses. Moving immediate PNG decode checks
to mandatory final-file verification provides writer headroom without weakening
pixel integrity. These settings remain explicit experimental overrides.

An uncorrected no-CPU-quota, 4 GiB run completed 20 x 40 seconds with all files
verified and zero source gaps/repeats. Its accounting gate FAILS: three pre-cutoff
wrist receipts arrived after immediate finalization and were not represented in
decisions. M09/M13 now implement bounded tail draining while preserving the exact
sample cutoff; an over-budget tail fails explicitly. The corrected candidate is
undergoing a separate full batch. This supersedes the earlier NOT RUN status:
duration/file checks have run, but final candidate acceptance is still pending.
The [resource/gate proposal](../m08-frame-matching/resource-gates.md) separates
experimental evidence, numerical gates awaiting alignment and production defaults.

Corrected candidate result: PASS against the proposed gates for 20 exact
40-second episodes in one persistent physical rig. All 23,995 wrist receipts
were accounted for, 23,945 groups accepted, and all files independently verified.
Source gaps/repeats, queue overflows and unaccounted anchors were zero. See the
[final measurements](../m08-frame-matching/resource-gates.md#final-candidate-results-2026-09-10).
M13-A03's physical duration/file case has passed on the experimental configuration;
numerical gate adoption, production defaults, semantic role binding and the
remaining full-module checks are not silently marked accepted.

The [latest wiring recheck](layout-recheck-20260910.md) passed the user-approved
six-episode scope. Seven episodes completed before the requested stop; the
report preserves the interrupted batch state. Both D435IF links were USB 2.1
in this test and still met the current 640x480/30 Hz capture gates.

## Read-only integration increment

Offline read-only integration passes native, amd64 Jazzy and source-free runtime checks. Two 2-second synthetic episodes completed with 60 image groups each and independently verified feedback. New-image real input acceptance remains NOT RUN; no lab access or control commands occurred during offline resumption. See the
[shared plan and results](readonly-integration.md).

## Independent controlled-batch audit

Keep native URSim recording and its final audit distinct. The audit must reject
an error-bearing report even if an earlier test step set a success flag. Require
exact episode count/duration, final-file verification with the current control
validator, no native source gaps/repeats, at least 99.5% accepted wrist decisions
per episode and 99.7% overall, and at most two consecutive rejected anchors.
Check contiguous decision identities and boundary coverage within 50 ms; never
use the weaker 28.5 Hz smoke floor as the final grouping-quality gate. Stored
outcome may honestly mark the last verified episode discarded by the lifecycle
test; this does not make it retained training data. Preserve all failed reports.

The audit reports maximum host receipt gaps separately. Its 50 ms coverage check
applies at episode boundaries; an internal callback interval is not a physical
exposure-clock measurement. Internal decision IDs must still be contiguous and
receipt order must advance. Synthetic scheduling jitter remains visible in the
original timestamps and rejection counts; it is never replaced with idealized
30 Hz timestamps. The optional LeRobot projection has its own stricter cadence
requirements and may reject an otherwise valid raw episode.

## Full controlled URSim batch result (2026-09-10)

M13-A03.sim **PASS**: `session-1789028767567594961` completed all twenty 40-second
URSim-controlled episodes with three persistent synthetic RGB-D sources. The
current independent audit also PASSes: 23,998 / 24,007 wrist decisions accepted
(99.9625%); worst episode 99.75%; maximum two consecutive rejections. All source
color/depth counters remain contiguous with no repeated depth observations.
Every complete MCAP reopens, all RGB decodes, every raw-depth hash matches, and
current authority/stream-coverage verification passes. The final episode is
intentionally marked discarded to test held review; it is not retained training
data. No failed or partial episode is counted toward twenty.

Writer peaks are 10/16 image triples and 68/128 small records; the latter exceeds
the old 64-record budget and supports the corrected simulator allocation.
Maximum observed queue delay is 339.03 ms. The maximum observed source receipt gap
is reported separately; synthetic producer scheduling is not uniform physical
exposure and no timestamp is replaced with an idealized value. All decision
identities and boundary coverage pass the independent audit.

The twenty MCAP files total 600,513,742 bytes. This easy synthetic image/depth
fixture is not a lab storage-cost prediction; previous physical-scene measurements
remain the useful deployment evidence. No physical camera, UR, Hand-E or GELLO
acceptance is inferred. The original frozen client used the previously tested
dependency image plus its recorded source overlay; current source-matched images
are validated separately. Full reports and failed predecessors remain under
ignored `artifacts/simulator-control/`.
