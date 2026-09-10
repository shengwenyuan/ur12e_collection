# M12: Independent Visual Calibration

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Module: M12
- Status: implementing; offline geometry/detection/checkpoint software accepted
- Parent: [meta plan](../../meta_plan.md#m12-independent-visual-calibration)
- Updated: 2026-09-10
- Dependencies: M06 motion ownership; [M03 feedback](../m03-ur-adapter/plan.md);
  [M07 cameras](../m07-camera-rig/plan.md); [M02 configuration](../m02-station/plan.md);
  M10 immutable episode metadata
- Authorization: autonomous simulator/offline sprint authorized on 2026-09-10;
  physical calibration or robot motion remains prohibited.

## Problem and agreed workflow

Provide a common world reference and traceable camera poses across episodes.
The D405 mount is fixed; the two D435IF cameras are frequently moved and cannot
be assumed to recover their previous extrinsics when approximately repositioned.
The reported millimeter-scale placement variation is not an accuracy guarantee.
The intended benefit is reduced untracked geometric variation in dataset use.
Calibration metadata does not itself normalize image viewpoints or establish a
VLM performance improvement. Extrinsics in a future model prompt remain an idea.

The user confirmed two separate rounds:

1. **Fixed-camera round:** Hand-E rigidly holds the board. A verified script
   moves UR through taught poses; stationary left/right cameras observe it.
   Estimate each camera's relation to the robot base and the held board's
   relation to the chosen robot end frame. Do not require a known board-to-tool
   mounting measurement or simultaneous visibility in both views at every pose.
2. **Wrist round:** secure the board on the table independently of the robot.
   A verified script moves the rigidly mounted D405 through suitable views.
   Estimate wrist-to-end-frame extrinsics and the stationary board's base pose.
   The board can move between rounds but must remain fixed within round 2.

Two rounds remove the requirement for D405 to see the gripper-held board.
They do not remove its focus, distance, field-of-view or corner-visibility
requirements for the tabletop board. Confirm these with the actual mount.

The user will manually teach key poses, verify safe motion, and convert them
to a fixed script. The first round is scripted too. Calibration depends on
image acquisition and actual pose readback at script checkpoints. It does not
plan new routes, search for poses or silently change the taught trajectory.

## Proposed interfaces and execution

These details are proposed implementation choices, pending controller inspection:

- Keep `ur-collect calibrate` separate from production episodes. Separate motion
  script execution, observation capture, offline solving and result activation.
  The offline solver requires no live connection or motion permission.
- The verified script is the only active motion source during calibration and
  must execute under M06 ownership and bounds. M12 capture/solve must not open
  an independent motion writer. UR-native versus host-side script execution
  and the checkpoint transport remain undecided.
- Associate each checkpoint with a round ID, pose ID, expected camera roles,
  joint target, route/script revision and capture/validation purpose. A script
  arrival/checkpoint signal must be verified against actual feedback. Provide
  a capture-complete acknowledgement or equivalent verified hold contract so
  the script cannot leave while the observation window is still active.
- After measured arrival and stability, acquire for two seconds. Motion time
  does not count. Reject stale robot state and images outside the stable window.
  Record controller and camera source times plus host clock association. Do not
  pair a commanded target or later pose read with an earlier image as truth.
- Select sharp images with sufficient board coverage from approximately 60
  candidates per pose. Several frames from one stop do not become independent
  geometric poses. Report accepted/rejected observations separately per camera.
- Keep the existing 20-40-pose total budget. Round allocation and held-out poses
  remain open; the earlier 15 solve + 5 validation poses per round is a proposal,
  not a confirmed count. Teach varied orientations around multiple axes and
  varied image coverage; final targets and routes require lab verification.
- Capture or script failure must not publish a successful calibration. Define
  bounded pause/abort behavior with M06; do not automatically skip to another
  motion, return to READY or release the board. Retry policy remains open.

## Geometry, solver and metadata

Propose UR base as the world reference and the mechanical flange as the stable
wrist mounting reference. Define `T_A_B` to map coordinates from frame B to A.
Store static `T_base_left_optical`, `T_base_right_optical` and
`T_flange_wrist_optical`; derive dynamic wrist world pose as
`T_base_flange(t) * T_flange_wrist_optical` using actual robot feedback.
The physical robot/base anchor must also remain unchanged for cross-run reuse.

M03 currently reads actual TCP pose. Before deriving flange pose, verify and
record the active flange-to-TCP transform and the controller's frame conventions.
TCP rotation vectors are not Euler angles. Use meters and radians, explicit
optical frame IDs, device identities and consistent transform directions.
Do not substitute nominal UR10e forward kinematics for verified UR12e feedback.

Prefer OpenCV 4.12.0 with ChArUco detection, PnP and hand-eye/robot-world solvers.
Board type, measured dimensions, dictionary, corner layout and print scale remain
to be finalized. Use factory RealSense intrinsics for the exact active image
profile initially; preserve distortion model, color/depth factory extrinsics,
depth scale and alignment convention. Image alignment is not cross-camera
extrinsic calibration. Keep selected calibration RGB images lossless.

Save source images, detected corner IDs/coordinates, actual robot observations,
script/board descriptions, rejected samples, solver settings and validation
report separately from the environment configuration. Active results reference
that evidence and record calibration ID/version, creation time, dependency
versions, device/mount identities and validity state.

## Repositioning and reuse

- Moving a D435IF invalidates its previous active extrinsics. Repeating a mount
  placement approximately or seeing the same serial is insufficient evidence
  for reuse. Re-run the fixed-camera round for affected views before claiming
  the new setup is calibrated. Keep each camera stationary through its run.
- Proposed reuse: retain D405-to-flange extrinsics while its mount is unchanged,
  subject to a validation check. Third-camera repositioning alone need not force
  a new wrist round. Remounting the wrist camera invalidates that relation.
- Bind episodes to immutable snapshots; a later calibration never rewrites old
  episodes. Retain previous results for provenance even when invalid for the
  current physical setup. A failed new solve must not reactivate a stale setup.
- Physical movement is not guaranteed detectable in software. Operator setup
  declaration, setup IDs and verification checks are proposed mechanisms.
  Exact UI, calibration-required startup policy and partial update behavior
  need M02/M09 alignment; no schema/runtime changes are made by this plan.

## Ordered implementation proposal

1. Confirm board geometry, robot frame/TCP readback and the script checkpoint
   contract; define a small versioned observation/result schema.
2. Implement offline detection, geometry solving and independent-pose reports,
   with known-transform fixtures and deliberately degenerate/noisy inputs.
3. Integrate M07 image capture and M03 actual feedback at verified stationary
   checkpoints. Keep capture usable independently of the solver.
4. Integrate the user-verified script through M06, then exercise both rounds
   in the lab with explicit visibility, timeout and stop handling.
5. Add M02 atomic activation and M10 snapshot binding; validate repositioning,
   reuse and failed-update behavior before production use.

Avoid a general-purpose calibration framework. Use small observation records,
explicit transform helpers and separate capture/solve/publish boundaries.

## Acceptance plan

| Case | Required evidence | Environment |
| --- | --- | --- |
| M12-A01 | Both verified scripts visit their configured checkpoints; actual arrival/stability gates each full two-second capture; capture never issues independent motion | Fixtures, then real UR and cameras |
| M12-A02 | Invisible/blurred boards, inadequate corners, stale state and interrupted captures produce explicit rejected observations and no false success | Recorded fixtures, then camera/robot checks |
| M12-A03 | Known transforms and directions recover correctly; degenerate motion is rejected; held-out real poses meet agreed reprojection and position/orientation thresholds; left/right estimates are consistent | Offline fixtures and real two-round observations |
| M12-A04 | Failed activation preserves prior stored results; moved-camera results remain invalid; valid replacement is atomic and old episode snapshots are unchanged | Filesystem/configuration fixtures, then a repositioned-camera run |

Numerical thresholds are deliberately pending. Report pixel residuals,
held-out board position/orientation consistency and per-camera observations.
Do not infer millimeter accuracy or task success from reprojection error alone.

## Alignment and current results

On 2026-09-09 the user confirmed two rounds, a fixed D405 mount, routinely moved
D435IF cameras, a common world-reference goal, rigid board fixation within each
round, and taught poses converted to scripts for both rounds. They requested this
documentation update and allowed remaining physical details to wait for the lab.
Implementation-specific proposals above have not been represented as approved.

The initial 2026-09-09 update was documentation only. The subsequent authorized
implementation and its software results are recorded below; physical gates remain
NOT RUN.

## Remaining lab decisions

Confirm controller connection/version, actual pose/TCP conventions, native or
host-side motion script and capture checkpoints; board geometry and fixation;
usable D405/tabletop and left/right/held-board views; taught routes and pose
allocation; hold/stability tolerances, failure behavior and accuracy thresholds.
Lab access is through `ssh ur12e-collection` when available; development must not
assume continuous connectivity. No remote connection is needed for this update.

References: [OpenCV hand-eye and camera calibration](https://docs.opencv.org/4.12.0/d9/d0c/group__calib3d.html),
[ChArUco detection](https://docs.opencv.org/4.12.0/df/d4a/tutorial_charuco_detection.html).

## Autonomous offline implementation scope (2026-09-10)

The [simulator sprint](../m13-acceptance/simulator-sprint.md) authorizes the
following concrete software increment without waiting for hardware decisions.
The earlier documentation-only authorization describes the preceding turn.

Implement separate `calibration/geometry.py`, `board.py`, `checkpoint.py` and
`results.py` responsibilities. Offline solving never imports a motion transport.
Use OpenCV 4.12 ChArUco/PnP and PARK hand-eye calibration. A shared solver uses
`T_base_flange` for the wrist round and its inverse for the fixed-camera round;
it returns respectively `T_flange_camera` or `T_base_camera`. Estimate the second
constant transform from training poses only. Verify on separately named held-out
poses; require at least six training and three validation poses per visible camera.
The overall taught-pose budget remains 20–40, with shared fixed-camera poses.

Inputs must specify board dimensions/dictionary, calibrated image intrinsics,
rigid transform directions, actual observed poses, unique checkpoint IDs, camera
serial/mount/base identities, source evidence and an explicit simulation flag.
Reject invalid rotations, repeated poses/IDs, insufficient multi-axis rotation,
missing held-out data and exceeded explicit accuracy thresholds. Thresholds are
required inputs, not invented physical accuracy guarantees. Report translation,
rotation and reprojection residuals separately; never fit to validation poses.
Planar board detection uses positive-depth PnP and records corner coverage and
reprojection error. Unsupported distortion models fail explicitly.

A pure checkpoint gate consumes actual joint feedback and image receipt times.
It requires measured target arrival and standstill before a full two-second
window, rejects stale/moving feedback and out-of-window images, and emits no
motion commands. Native script/checkpoint communication and physical board
visibility remain deferred. Synthetic images exercise detection; synthetic known
rigid transforms exercise both geometry directions and held-out rejection.

Activation will validate evidence and setup identities before atomically replacing
the selected calibration configuration. A failed activation leaves the previous
file unchanged. Old snapshots retain their copied content. Physical camera/mount
changes require a fresh declared setup identity; software cannot detect an
unreported physical relocation. Any station-schema integration is tested after
the currently running frozen-behavior M09 long batch completes.

Acceptance mapping: M12-A01/A02 pure checkpoint and image tests; M12-A03 both
known-transform recovery, degenerate poses, noise and held-out failures;
M12-A04 immutable result/atomic activation tests. All physical M12 gates remain
NOT RUN. AprilGrid remains a later detector option; ChArUco is the first backend.


## Offline geometry, detection and checkpoint results (2026-09-10)

Implemented explicit SE(3) validation and UR rotation-vector conversion,
fixed/wrist PARK hand-eye solving, independent held-out residuals and observability
checks. ChArUco detection uses measured board scale, supported camera optics,
corner coverage, sharpness, positive depth, planar ambiguity and reprojection
checks. The stationary checkpoint class has no motion writer and requires actual
arrival, settling, fresh preceding image-pose association and a two-second dwell.

`pytest -q tests/test_calibration.py`: **19 PASS** on Mac Python 3.12 / OpenCV
4.12.0. Black and module Pylint **10.00/10 PASS**. Tests cover both known-transform
directions, realistic small synthetic measurement perturbations, held-out-only
errors, repeated IDs, identical/single-axis degeneracy, invalid rotations,
rendered ChArUco pixels, blur/visibility/unsupported optics, full dwell boundaries,
motion during dwell, stale feedback and a later pose incorrectly paired to an image.

- M12-A01/A02: offline checkpoint and image portions PASS. Native checkpoint
  transport, board fixation and real camera/robot capture NOT RUN.
- M12-A03: synthetic geometry/detection portions PASS. Physical accuracy,
  factory distortion compatibility and independent real-pose validation NOT RUN.
- M12-A04: result persistence, activation and station/snapshot integration remain
  pending in the next increment. No active calibration has been installed.

The synthetic test tolerances are software gates only. No printed board geometry,
physical mounting measurement, safe taught route or physical calibration accuracy
has been inferred from these results.
