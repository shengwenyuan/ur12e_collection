# M12: Flexlab D435 Replay Delivery

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implementation complete; image deployment and physical acceptance pending.
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
| right / 327122075735 | 35.27, -65.29, -125.81, -90.00, 90.00, -0.64 | 368.46 s |

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
- M01 image/source identity and installed Ubuntu regression: pending.
- Printed dimensions, current camera visibility, physical path clearance and
  millimeter accuracy: NOT RUN; no hardware control sent.
