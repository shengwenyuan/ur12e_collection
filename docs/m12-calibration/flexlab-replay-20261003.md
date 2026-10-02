# M12: Flexlab D435 Replay Delivery

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: offline deployment accepted; physical replay acceptance pending.
Aligned 2026-10-03. Target confirmed by the operator: the current
`ssh ur12e-collection` destination, `robot2026fall@ur12e-flexlab`, not `li1013`.
No calibration motion or collection session is started by this delivery.

## Imported teaching

Source: colleague repository `7cd6dea`, each camera's
`data/camera_N/handeye/waypoints/waypoints.yaml`. Import preserves all 30 measured
joint targets in order. Waypoints 6, 12, 18, 24 and 30 are frozen as validation
before new acquisition; the other 25 are fitting poses. Old images, intrinsic
coefficients and computed TCP/flange transforms are not reused as measurements.
The source YAML and its SHA-256 remain beside each canonical route.

The default board is the original PDF. Each imported route embeds its full
layout so later board changes cannot silently reinterpret it. Setup-generation
names assigned for this run are provisional deployment identities, not evidence
that the board or camera has remained physically fixed since teaching. The
operator must confirm the current mounting/print before launch. No automatic
station activation is performed by deployment.

The source's calibration center was redefined during teaching; it is not the
first pose. Require waypoint 1 as the manual start. Never add an automatic
HOME-to-center or left-to-right connecting move.

| Route | First joints in degrees (base, shoulder, elbow, wrist1, wrist2, wrist3) | Nominal total |
| --- | --- | --- |
| left / 327122073926 | -19.778, -89.993, -89.990, -89.994, 90.003, -134.598 | 423.80 s |
| right / 327122075735 | 35.266, -65.290, -125.813, -89.996, 90.003, -0.637 | 368.46 s |

Estimates use 3 degrees/s and 6 degrees/s², per-segment acceleration/deceleration
and two seconds of stationary capture per pose. Camera warmup, measured settling,
controller speed scaling, the post-stop hold observation and solving add time.
The largest adjacent joint changes are 72.65 degrees (left, entering waypoint
27) and 73.13 degrees (right, entering waypoint 23). These are substantial joint
interpolations, not tiny perturbations around HOME. Manual teaching evidence
does not establish that the connecting `moveJ` paths are collision-free.

## Provisioning and operation

The importer is an offline developer tool using pinned PyYAML; the runtime only
consumes canonical JSON. Example import (repeat with the right role/source):

```sh
python scripts/import_calibration.py \
  --source /path/to/camera_2/handeye/waypoints/waypoints.yaml \
  --role third_left --config config/teleop.ur.json \
  --station config/local/recording.station.json \
  --base-id ur12e-base-20261003 --mount-id third-left-20261003 \
  --board-mount-id held-board-20261003 \
  --output ~/ur12e-calibration/third_left/routes/colleague-20260926.json
```

Provision `config/local/calibration.json` from the example with both route paths.
Existing robot, camera, leader and recording configurations must be preserved.
This delivery does not change production station calibration/setup declarations.

Device-free preview, safe before robot startup:

```sh
ur12e cali --left --validate-only
ur12e cali --right --validate-only
```

Only after operator alignment on the board, manually reached start and cleared
path, run one camera at a time:

```sh
ur12e cali --left --replay --operator-approved
# After the first run finishes and the operator manually reaches the right start:
ur12e cali --right --replay --operator-approved
```

The configured camera starts and warms up before control ownership is acquired.
Replay requires the measured arm to be within the configured arrival tolerance
of the printed start (currently 0.1 degrees on every joint). It visits 30 targets
in order, verifies standstill, then collects two seconds at each target. Progress
prints checkpoint/state changes. The board can leave view during transit; each
stationary checkpoint needs a valid fresh image. Hand-E keeps its grasp; no
opening/closing command is sent. The last waypoint is the endpoint; there is no
automatic return. Ctrl+C interrupts through the shared verified stop path and
retains partial evidence, without resuming or advancing to another pose.

After verified shutdown, the fresh run is solved and independently validated.
Failure retains raw data for diagnosis and does not activate a result. A
completed capture is not necessarily a successful calibration. Declaring setup
and activating results is a separate explicit action after reviewing the output.

## Acceptance

- M12-A01: imported left/right route structure, order, counts and joint bounds
  PASS offline; physical replay NOT RUN.
- M12-A02/A03: native 480p rendered-pixel, PDF geometry, held-out isolation,
  nonzero TCP conversion and fixed/wrist numerical tests PASS on Mac. AprilTag
  edge refinement replaces generic subpixel refinement, matching the colleague's
  detector approach. Production accuracy gates remain unchanged.
- M12-A04: corruption, activation identity mismatch and prior-result retention
  PASS offline. Keyboard teaching is intentionally outside this import/replay
  increment, because existing teaching is being reused.
- M01 image/source identity and installed Ubuntu regression: PASS below.
- Printed dimensions, current camera visibility, physical path clearance and
  millimeter accuracy: NOT RUN; no hardware control sent.

## Completed software delivery

- Implementation commit: `04036fc6ba225130332d5ef4c275f028fcbf6304`.
  Later acceptance documentation does not change its executable content.
- Mac native checks: Black PASS (212 files), Pylint PASS (10.00/10), pytest
  707 PASS / 5 SKIP. The final CLI isolation and activation subset also passed.
- Image: `ur12e-collection:current`, also tagged `cali-04036fc`, identical on
  Mac Docker Desktop and Flexlab:
  `sha256:1537f9df1cd1d0ca5cb68c10efeeab959d6b45abadfa33463b5791a6beff116b`.
  Platform linux/amd64, Ubuntu 24.04 / ROS 2 Jazzy / Python 3.12, OpenCV
  4.12.0.88 and NumPy 2.2.6. Build reused the existing image layers with build
  networking disabled. Only the 768 kB pinned development PyYAML wheel was
  fetched in addition to the locally built collector wheel.
- Installed-package tests: 710 PASS / 2 SKIP on both Mac's Ubuntu container and
  the actual PC. Runs used no network or device mounts, non-root user and
  read-only root. The first Mac run had one ROS logging failure because the
  read-only home lacked a writable log directory; setting
  `ROS_LOG_DIR=/tmp/ros-log` corrected the test environment and the full rerun
  passed. No application gate was relaxed.
- M01-A01 PASS: all 120 installed package files match source hashes; image,
  source archive and hash-manifest transfer checksums passed. The archived image
  SHA-256 is `cdfa952eecaa4b59fdb37e5819de5cbdc7488487610122f17035e0b203efa17a`.
- M12-A01 PASS software: both imported 30-point routes completed the actual
  traversal/owner with synthetic device feedback. All 60 targets retained their
  order, speed/acceleration and two-second dwell; no hardware commands were sent.
- M01-A03 PASS: actual `ur12e cali --left --validate-only` and `--right
  --validate-only` work from `/tmp` on the PC through the deployed image and
  configured routes. They report `motion_ready=false`, not physical acceptance.
- Eight existing station configuration files remained byte-identical. Only the
  new calibration path configuration/example and imported route tree were added.
  Existing recordings and production calibration declarations were not modified.
- Source/config backup:
  `/home/robot2026fall/past_archives/before-cali-04036fc-1790967205349626997`.
  Prior image retained as `ur12e-collection:before-cali-04036fc`.
- Reproducible local logs and route previews live in ignored
  `artifacts/calibration-20261003/`; PC delivery archive/receipt:
  `~/ur12e-deliveries/cali-04036fc/`. Routes and future observations live under
  `~/ur12e-calibration/third_left/` and `third_right/`.

No device-reading calibration run, robot motion, gripper command or collection
session was launched. The next action is operator alignment on first starts,
current board visibility and the substantial point-to-point paths, then a
supervised left replay followed by a separately positioned right replay.
