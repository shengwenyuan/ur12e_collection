# M12: Camera-Specific AprilGrid Replay and Calibration

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / acceptance pending, 2026-09-15. The user explicitly authorized replay and
calculation assuming colleague-supplied waypoint JSON files. Keyboard teaching
and IK generation are deferred. This authorizes software work and local tests;
physical execution still needs a separately supervised operator launch.
Dependencies: M02 configuration, M03 actual pose/offset, M06 exclusive motion,
M07 images and M10 provenance. Existing unrelated development is preserved.

## Confirmed requirements

- Replace GELLO-based calibration teaching with keyboard control. Smooth human
  motion is unnecessary; usable, detected calibration checkpoints are the goal.
- Use 20-30 capture poses for each camera, in separate reusable JSON files. The
  user calls these waypoints; separate transit-only points need not exist in the
  ordinary route. Never create placeholder poses just to meet the count gate.
- Consider local pose variations beginning with wrist3 and IK-generated targets.
  The user will supervise first execution of the complete route.
- Provide mutually exclusive `ur12e cali --left`, `--right`, and `--wrist`
  entries. Replay requires an existing valid camera-specific JSON with at least
  20 capture checkpoints. This count gate does not apply while teaching a new file.
- Acquire one stationary-image rollout per camera. Solve intrinsics first, then
  extrinsics from the same new observations; do not require a second physical
  rollout just because there are two numerical stages. No trusted RGB intrinsic
  calibration is supplied by the user.
- Use the supplied AprilGrid PDF printed at actual size and bonded to backing.
  Target millimeter-level positioning and shared multi-view coordinates, with
  later geometric visibility analysis as a consumer. The agreed translation-consistency target is <=2 mm, without automatic
  relaxation. Fixed cameras observe the worktable from about 1 m; wrist views
  the fingers and nearby workspace within 20 cm. Absolute accuracy still needs
  independent physical measurement.

## Inspected board definition

Source filename: `aprilgrid_Letter_tag36h11_4x6_28mm_actual_size.pdf`.
SHA-256: `8112bee13432c86b77a6914ec7141ded26e3c0604308dac3869f3678d164fe01`.
The one-page US Letter PDF contains `aprilgrid_configuration.json` and a license.
Its declared geometry is tag36h11, four columns, six rows, 28 mm outer black tag
edge, 8.4 mm gap (ratio 0.3), and a 137.2 x 210 mm grid. IDs are
`4 * row_from_bottom + column_from_left`, 0-23. Origin is tag 0's lower-left
outer black corner; +X is right, +Y is up, and +Z completes the right-handed frame.
All PDF tags are rotated 180 degrees relative to OpenCV-generated markers.
Decoded corner order is therefore board bottom-right, bottom-left, top-left,
top-right. This was verified against all 24 tags in the supplied PDF rendering;
the rendering and embedded license are retained as a regression fixture.

Read-only PDF inspection PASS: rendered page inspected; pinned project OpenCV
detected all 24 IDs in the expected layout. This proves compatibility of the PDF
render, not physical print accuracy or camera visibility. Measure the printed
100 mm ruler, horizontal/vertical spans and tag edges; bonding must not warp the
board. Preserve nominal and measured geometry separately. The PDF's historical
93 1/3% generation scale must not be applied again during printing.

## Deferred teaching and implemented route contract

Future teaching work may add `--teach` for keyboard teaching under the same selected camera entry, and
an optional explicit `--poses FILE`; defaults resolve by role from deployment
configuration, independent of the shell's working directory. A final valid route
might be invoked as `ur12e cali --left --poses left.json`. The replay form is implemented with required `--poses`, `--output` and explicit
`--operator-approved`; only the future teaching flag remains unimplemented.
The current file contract is documented in [replay usage](replay-usage.md).

Keyboard increments are bounded joint or Cartesian pose requests. Direct joint
jogging needs no IK. Cartesian requests need an IK solution seeded from the
previous actual joints, preserving branches and rejecting large jumps, limits
and singular/unreachable candidates. IK finds a joint solution; it is not a
collision planner. The IK provider and keyboard increments remain design choices
for alignment. Do not blindly traverse every analytic IK branch.

Begin near a visible board pose, but require varying tilt about at least two
nonparallel axes, distances and image-plane coverage. Wrist3-only rotation or
many almost-identical poses cannot satisfy calibration observability simply by
reaching 20 entries. No intrinsics are needed to detect IDs and image corners;
3D board pose/reprojection checks become available after intrinsic estimation.
Initial acceptance uses IDs, corner support, sharpness, coverage and fresh
stationarity, without fabricated intrinsics.

Save ordered actual UR joint positions in radians, role/serial, board and setup
identity, reference frames, bounded motion settings, capture/validation split and
start/end path conditions. The saved joints are targets only on later replay.
Preflight the full route and start before motion. The first real replay needs
operator supervision; later reuse requires unchanged scene/mount/clearance.
If an adjacent move cannot be accepted, reorder/reteach it or explicitly add a
transit segment. Never silently invent a bypass or assume endpoint visibility
proves path clearance. Route selection or JSON inspection alone sends no motion.

## Capture and two-stage solution

Keep the left/right cameras stationary with the board rigidly held by Hand-E.
For wrist calibration, fix the board to the table and move the mounted D405.
Each camera can have its own route/run; no simultaneous visibility is required.
The common world reference is the UR base, not a supposedly unchanged board pose
between runs. Keep camera/board attachment constant within each run.
Calibration teaching/replay must retain the gripper's board grasp and ignore
leader gripper inputs. In particular, ordinary collection HOME auto-opening must
not be reused for a board-holding calibration round.

Reuse exclusive motion ownership, bounded movement and stopping. After measured
arrival and stable actual feedback, collect a two-second window from persistent
RealSense streams. OpenCV detects/scores images; it does not own the camera or
robot connection. Store lossless RGB, detected IDs/corners, raw actual joints and
TCP pose, source/receipt timestamps, pose variation and offset provenance.
Reject pre-arrival buffered exposures, stale robot packets and moving windows.
Associate fresh actual readback with each image; a robust window estimate may
supplement but never replace raw evidence. Joint targets from route JSON are
never solver measurements. Fresh feedback addresses repeatability error, not
unmeasured structural flex, board motion or robot kinematic bias.

Optical scope: explicit RGB8/30 Hz modes, default 1920x1080 for fixed
cameras and 1280x720 for D405, checked against actual SDK profiles before motion.
D405 1288x808 is a special stereo calibration mode, not a promised RGB8 mode.
Allow explicit 640x480 calibration. Never resize observations or apply a
16:9 intrinsic matrix to the 4:3 production stream. Results are mode-bound and
not automatically activated; production remains 640x480. Retain factory
depth/stereo calibration and SDK alignment. Do not overwrite
factory parameters or silently change RGB/depth registration. Any SDK intrinsic
values read during acquisition are comparison metadata, not trusted fit inputs.

1. Detect AprilTag corners and fit RGB intrinsics/distortion from nominal or
   measured board coordinates without relying on prior K. Check diversity and
   conditioning; avoid adding unsupported high-order distortion coefficients.
2. With fixed fitted intrinsics, obtain per-image board poses and solve fixed
   camera-to-base or wrist-camera-to-flange extrinsics using actual robot poses.
   Convert frame directions explicitly; planar ambiguity remains a rejection
   concern. Existing ChArUco-only detection is not an AprilGrid implementation.
3. Proposed default: 25 checkpoints, 20 fit and five spatially distinct held-out
   checkpoints. Held-out images participate in neither intrinsic nor extrinsic
   fitting. Multiple frames at one checkpoint are not independent poses.
4. Report held-out image residuals, metric consistency, pose diversity and
   working volume. Low pixel reprojection alone does not prove absolute 1 mm
   accuracy; independent dimensional/position evidence is required for that claim.
   Translation consistency is gated at <=2 mm; an independent physical
   reference method remains to be selected.
5. Preserve each raw run and publish a versioned result only after verification.
   A failed solve leaves the prior calibration intact; insufficient evidence
   requires targeted additional poses, not blind repetition of the same route.

The calibration runtime now queries/persists the active TCP offset under
authorized SDK ownership. The M03/M10 read-only MCAP offset acquisition TODO
remains separate; this increment does not retrofit prior recordings. A declared zero Installation TCP and a physical 127 mm tool
extension are different quantities. Do not use the latter as flange-to-board
geometry or reuse old zero-offset claims without current provenance. Common
multi-view transforms enable geometric frustum tests, not guaranteed visibility
through unknown occluders or improved depth accuracy by themselves.

## Implementation sequence and acceptance

1. Implement AprilGrid geometry/detection and two-stage intrinsic/extrinsic tests.
2. Define the role-specific route schema and validation gates; defer teaching.
3. Connect supervised replay to existing control ownership, camera capture and
   actual-pose/offset evidence. Provide CLI help and a colleague-facing JSON contract.
4. Validate stopping, clock/visibility failures, immutable evidence and atomic
   calibration activation offline and in isolated simulation.
5. Perform separately authorized real teaching/replay, print measurements and
   independent metric validation before claiming physical calibration acceptance.

| Stable gate | Required evidence | Current result |
| --- | --- | --- |
| M12-A01 | Existing >=20 checkpoint JSON; valid role/route; measured two-second capture; no target substituted for readback | PASS software; physical NOT RUN |
| M12-A02 | Known IDs/corners; blur/coverage/degeneracy/stale-frame rejection; no K required for initial detection | PASS PDF and software; real camera NOT RUN |
| M12-A03 | Two-stage solver, withheld-pose validation and independent millimeter accuracy assessment | PASS numerical software; physical accuracy NOT RUN |
| M12-A04 | Failed acquisition/solve never replaces valid calibration | PASS immutable replay/result software |
| M03-A01 / M10-A03 | Actual pose and offset provenance, frames and timestamps remain traceable | Calibration query/conversion PASS software; physical offset and MCAP TODO remain |
| M06 / M09 | One owner, no HOME auto-opening in board mode, invalid route sends no movement, stop/fault/restart boundaries | PASS software; physical NOT RUN |

References: [OpenCV 4.12 camera/hand-eye calibration](https://docs.opencv.org/4.12.0/d9/d0c/group__calib3d.html),
[Kalibr target conventions](https://github.com/ethz-asl/kalibr/wiki/calibration-targets).

## Approved replay/calculation increment

Implement `ur12e cali --left|--right|--wrist --poses FILE` with explicit
`--validate-only`, `--operator-approved` for replay, and offline `--solve RUN`.
The canonical JSON contract is documented in `replay-usage.md`; validate the
entire route, camera/setup identities, joint order, radians, start tolerance,
20-40 unique capture checkpoints and >=5 held-out checkpoints before connecting.
The configured READY speed/acceleration bound each route segment. Start mismatch
rejects motion; no implicit HOME, return route, IK, gripper opening or resume.

Reuse M06 Controller/Traversal and physical Transport, including exclusive host
lease, watchdog and verified shutdown. A separate camera process owns RGB capture,
detection and PNG encoding. The motion owner only consumes bounded messages and
retains one selected frame per checkpoint, keeping OpenCV and image file writes
outside its loop. Capture failure or interruption aborts without advancing.
Use new actual RTDE poses and a freshly queried active TCP offset, queried only
inside explicitly authorized control ownership, to derive base-to-flange.
Preserve offset before/after, actual joint/TCP readback, clocks, frames, route,
stream identity and a stop/fault trace. No assumed zero or 127 mm substitution.

Fit a five-coefficient Brown model using training views only. Require >=15
training and >=5 held-out views (20 minimum total), nondegenerate rotations,
positive-depth/unambiguous PnP and per-view pixel/metric gates. Translation <=2 mm,
rotation <=1 degree and reprojection <=1 px are the initial numerical gates;
only translation is the user's physical accuracy target. Report per-view
residuals and intrinsic uncertainty. Do not equate self-consistency with absolute
physical accuracy. Missing/invalid views abort or fail solving; never silently
drop held-out samples or relax gates. Result bundles copy/hash raw evidence,
recompute verification, publish immutably and never edit active station data.

Software acceptance includes known-camera synthetic fixed/wrist geometry, real
rendered AprilTag pixels, corrupt/degenerate/insufficient data, no held-out leakage,
actual-versus-target semantics, nonzero TCP offset, stale/pre-dwell images, full
20-point replay, faults/interruptions and no gripper commands. Deployment, real
stream support, measured print dimensions and <=2 mm physical accuracy remain
NOT RUN until separately authorized lab work.

## Implementation and software acceptance (2026-09-15)

- M12-A01: role-specific 20-point replay PASS with the shared M06 owner and
  measured two-second dwells. Tests verify actual readback differs from stored
  targets, nonzero TCP offset conversion, READY rate limits, declared-start
  rejection and no gripper targets. Runtime tests verify camera/interrupt/offset
  faults stop and close ownership before camera cleanup, leaving partial evidence.
- M12-A02: original PDF image detects all 24 tags with correct rotated-corner
  geometry; rendered camera images, blur rejection, pre-dwell/stale readback
  rejection and bounded camera-liveness handling PASS. Near-frontal planar
  ambiguity was encountered in an early synthetic fixture and correctly rejected;
  the fixture was corrected to provide observable tilt, without relaxing gates.
- M12-A03: both fixed and wrist known-camera two-stage solves PASS with no prior
  intrinsics. Full 20-image PNG solve/copy/reverify PASS; withheld pixel changes
  cannot affect fitted K, and held-out geometric errors/degeneracy are rejected.
  <=2 mm applies to numerical consistency; absolute physical accuracy NOT RUN.
- M12-A04: corrupt evidence and existing-output preservation tests PASS. A failed
  capture remains partial; a failed numerical solve preserves the completed raw
  run and never changes active station calibration.
- Default replay automatically solves after motion cleanup. Offline solve and
  verification, malformed input, help and JSON validation never open devices.
  Shared Docker image selection/restrictions are reused by collection and
  calibration launchers. Current deployed images have not been changed.

Validation environment: Mac arm64, Python 3.12.13, OpenCV 4.12.0, pinned project
dependencies. Final regression and formatting/lint results are recorded below.
The first sandboxed full run had 684 PASS / 5 SKIP / 5 failures because POSIX
shared-memory allocation was denied. An unsandboxed software run subsequently
passed 691 tests with five skips, before adding the PDF orientation regression.
No lab SSH, real camera connection or robot command was executed.

Remaining: colleague route/schema integration, actual RGB mode enumeration and
throughput, first supervised replay with fixed board/mount, measured print
geometry, independent <=2 mm reference checks, production-mode calibration and
explicit activation. High-resolution schema-2 results remain separate from the
legacy ChArUco activation format. Keyboard teaching/IK are outside this increment.

Final software checks: **692 PASS, 5 SKIP** (`.venv/bin/pytest -q`, 13.35 s,
local execution with POSIX shared memory permitted). The skips are three ROS
checks unavailable in the Mac environment and two opt-in container checks.
Black: **PASS**, 207 files unchanged. Pylint: **PASS**, 10.00/10 with no messages.
`git diff --check`: **PASS**. The two new AprilGrid/replay test files contribute
38 passing cases, including the original-PDF orientation regression. Hardware,
image rebuild/deployment and absolute-accuracy acceptance remain **NOT RUN**.

## Calibration-only commit verification (2026-09-15)

The selected Git index was exported into an isolated temporary checkout, with
its own source path used for all checks. This excludes the unrelated pending
task-routing, HOME-opening and stop-budget changes. The calibration-only tree
passed **668 tests, 5 skipped** in 13.92 s; Black passed for 206 files and Pylint
passed at 10.00/10 without messages. The earlier 692-test result refers to the
combined working tree, not this isolated commit. The 25 selected files/hunks
passed diff checks and a limited credential-pattern scan; no temporary plans,
station configuration or unrelated control changes are included.
