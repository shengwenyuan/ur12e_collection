# M12 AprilGrid Replay and Two-Stage Calibration

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Implementation contract, 2026-09-15. The [formal plan](keyboard-aprilgrid.md)
records scope and acceptance. Teaching and IK generation are separate work;
this workflow accepts a colleague's already reviewed, ordered joint route.
Software tests are not authorization or evidence for physical motion.

## Entry points

`ur12e cali --left`, `--right`, and `--wrist` select exactly one camera.
The host entry is `scripts/ur12e.py`; its physical branch launches the current
Ubuntu Docker image. Rebuild/provision that image before lab use. It exposes
only cameras, the shared controller lease, configuration and the output parent;
no GELLO serial device is required. Installed package equivalent: `ur-collect cali`.

Offline preflight (no device connections):

```sh
ur12e cali --left --poses /absolute/path/left.json --validate-only
```

The host entry defaults `--config` and `--station` to deployment
`config/teleop.ur.json` and `config/local/recording.station.json`. Override them
explicitly when needed. Package entrypoints require both for replay/validation.
The selected camera and robot serial must match configuration. When a station
setup declaration exists, base and mount IDs must also match.

Future, separately authorized and supervised physical launch:

```sh
ur12e cali --left --poses /absolute/path/left.json \
  --output /absolute/path/calibration/left-run-001 --operator-approved
```

The operator must first place the arm at `start_q`, with the route cleared and
board secured; no automatic move to the start is added. READY speed and
acceleration from the reviewed physical profile bound every moveJ segment
(currently 3 degrees/s and 6 degrees/s²). The last capture pose is the endpoint;
there is no implicit HOME/return or gripper opening. Ctrl-C or SIGTERM stops
through the existing owner, verifies standstill and observes the post-stop hold.
A fresh launch starts the entire route; partial runs are never resumed.

The launch records one run, closes motion ownership, then automatically solves
intrinsics and extrinsics, producing sibling `left-run-001.result`. The raw run
survives a failed solve. Offline re-solving or verification never connects to a
robot or camera:

```sh
ur12e cali --left --solve /absolute/path/calibration/left-run-001 \
  --output /absolute/path/calibration/left-result-002
ur12e cali --left --verify /absolute/path/calibration/left-result-002
```

## Canonical waypoint JSON

Use production role names: `third_left`, `third_right`, `wrist`; CLI flags are
short aliases. Schema 1 is deliberately strict: unknown fields are rejected,
angle units are explicitly `rad`, and the joint order below is mandatory.
Each file has 20-40 **distinct capture** targets, >=15 training and >=5 validation
points. Prefer 25 points (20 training + 5 validation). Include two-axis tilt,
different distances and image coverage. Validation poses must be independently
chosen, not repeated frames/duplicates of training stops.

The fragment below shows fields, not an executable 20-point route. Replace
identities and all taught angles with measurements from the actual station.
Never duplicate placeholder poses to pass the count gate.

```json
{
  "schema_version": 1,
  "role": "third_left",
  "camera_serial": "ACTUAL_CAMERA_SERIAL",
  "camera_model": "D435IF",
  "robot_serial": "ACTUAL_ROBOT_SERIAL",
  "base_id": "station-base-v1",
  "mount_id": "left-mount-v1",
  "board_mount_id": "board-grasp-v1",
  "board_attachment": "flange",
  "joint_names": ["base", "shoulder", "elbow", "wrist1", "wrist2", "wrist3"],
  "units": "rad",
  "start_q": [0, -1.57, -1.57, -1.57, 1.57, 0],
  "profile": {"width": 1920, "height": 1080, "fps": 30, "format": "rgb8"},
  "board": {"tag_m": 0.028, "gap_m": 0.0084},
  "waypoints": [
    {
      "pose_id": "capture-001",
      "q": [0, -1.57, -1.57, -1.57, 1.57, 0],
      "split": "training"
    }
  ]
}
```

- `q` and `start_q`: measured, unwrapped UR joints used as future move targets.
  `start_q` is a required precondition, not an extra movement instruction.
- `via`: optional list of six-joint transit targets within a capture entry,
  traversed in order before `q`. They do not count as calibration views.
- `split`: `training` or `validation`; fixed before acquisition. Neither
  intrinsic nor extrinsic fitting uses validation images.
- `board_attachment`: `flange` for fixed cameras; `base` for wrist with the board
  independently fixed to the table. `board_mount_id` identifies that rigid setup,
  not a claimed known board-to-flange transform; the solver estimates it.
- `board`: measured outer black edge and inter-tag gap in **meters**. The fixed
  board layout is tag36h11, 4 columns x 6 rows, IDs 0-23 ascending right then up.
  Decoded tag corners map to bottom-right, bottom-left, top-left, top-right
  because this PDF rotates each tag 180 degrees relative to OpenCV defaults.
  Nominal geometry is 28 mm / 8.4 mm. The PDF source hash and frame convention are
  in the formal plan. Measure the actual print and preserve its mounting identity.

## Resolution and reference frames

At the reported ~1 m fixed-camera distance, prefer 1920x1080 RGB8/30 Hz.
For the wrist's <=20 cm working distance, use 1280x720 RGB8/30 Hz if the actual
D405 SDK stream supports it. The file explicitly selects a mode; there is no
silent fallback. D405 1288x808 is a special stereo calibration mode and is not
assumed available as RGB8. Both roles can explicitly use 640x480; fixed cameras
also permit 1280x720. Actual selected profile must match before control startup.

This workflow streams only RGB for calibration. Normal collection remains
640x480 RGB-D/30 Hz with SDK depth alignment unchanged. A high-resolution result
is bound to its RGB mode. Do not rescale a 16:9 camera matrix into a 4:3 image.
A result at 640x480 is merely pixel-profile-compatible, not automatically active.
Schema-2 results are intentionally not accepted by the legacy ChArUco schema-1
activation API. Production profile calibration/verified pixel mapping and
explicit activation remain separate follow-up work, not a claim of this result.

Transforms are `T_A_B` mapping B coordinates into A, translation in meters:

- Fixed camera: `T_base_camera`, plus estimated constant `T_flange_board`.
- Wrist: `T_flange_camera`, plus estimated constant `T_base_board`.
- Raw robot TCP uses UR rotation vectors, not Euler angles. Inside authorized
  ownership, query the current TCP offset before replay and confirm it unchanged
  afterward. For every selected image compute
  `T_base_flange = T_base_tcp @ inverse(T_flange_tcp)` from fresh readback.
  No historical zero-offset assumption or nominal 127 mm substitution is used.

## Capture, solve and evidence

A separate camera process captures, detects and PNG-encodes frames. Its bounded
queue cannot make OpenCV run on the 120 Hz control owner. The owner retains one
sharp valid frame per pose; image files are written after motion cleanup. A
trace writer independently records feedback/fault/stop events. Two seconds of
stationarity are checked at each pose; captured images must have an exposure in
that dwell, a fresh preceding actual robot sample (<=50 ms), and SDK global-time
provenance. Pre-arrival buffers and missing views fail rather than advancing.
Visibility in transit is optional; visibility during each capture is required.

`run.json` and lossless `images/*.png` preserve the route, limits, actual joint/TCP
readback, flange transform, before/after offset, camera identity/profile, image
source/receipt times and two-second dwell. `control/trace.jsonl` contains motion
and shutdown evidence. Interrupted acquisition remains in `RUN.partial` with
selected images and partial measurements and cannot be solved as a completed run.

OpenCV 4.12 fits a five-coefficient Brown model without prior K, then estimates
board pose using positive-depth and planar-ambiguity checks. The existing PARK
hand-eye solver checks rotational observability and held-out consistency.
Initial numerical gates are <=2 mm translation consistency, <=1 degree rotation
and <=1 px per-view reprojection. Insufficient data, bad conditioning, blur,
missing corners and any rejected held-out view fail the solve; gates never relax
automatically and points are not silently dropped. Correct near-frontal
ambiguity by adding tilted views, not by accepting an arbitrary PnP branch.

Each result copies and hashes its raw image/measurement evidence and recomputes
both stages during verification. Publishing never replaces an existing bundle
or active station calibration. Results explicitly report
`absolute_accuracy_verified=false`: passing metric consistency is not an
independent <=2 mm absolute-accuracy measurement. Physical validation must use
measured board geometry and independent reference positions throughout the
working volume before claiming that accuracy.

References: [OpenCV calibration](https://docs.opencv.org/4.12.0/d9/d0c/group__calib3d.html),
[RealSense D400 datasheet](https://realsenseai.com/wp-content/uploads/2025/08/Intel-RealSense-D400-Series-Datasheet-August-2025.pdf),
[ur_rtde active TCP offset API](https://gitlab.com/sdurobotics/ur_rtde/-/blob/master/include/ur_rtde/rtde_control_interface.h).
