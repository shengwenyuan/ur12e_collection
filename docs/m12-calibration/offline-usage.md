# Offline Calibration Commands

The commands below use local files only. They do not start cameras, execute a
robot script or send a motion command. Physical capture/checkpoint integration
remains pending; the current solver consumes recorded observations.

```sh
ur-collect calibrate setup --station /config/station.json --input setup.json
ur-collect calibrate solve observations.json --output /data/calibration/run-001
ur-collect calibrate verify /data/calibration/run-001
ur-collect calibrate activate /data/calibration/run-001 --station /config/station.json
```

A setup declaration contains `base_id`, `simulated` (a boolean), and `mounts`
with explicit `wrist`, `third_left` and `third_right` generation identifiers.
Use a new mount identifier whenever the corresponding camera is repositioned.
A changed base identifier invalidates every active result. Setup declaration
removes affected extrinsics; it cannot establish that a physical mount stayed put.
Never label physical observations simulated merely to bypass image requirements.

Each observation input describes one camera and contains:

- `schema_version: 1`, `simulated`, `role`, `camera_serial`, `base_id`, `mount_id`,
  and `script_revision` identifying the taught capture route.
- `board`: `squares_x`, `squares_y`, `square_m`, `marker_m`, `dictionary`.
  Dimensions are measured meters; `DICT_4X4_50` is one supported dictionary.
- `intrinsics`: exact 640x480 color profile, `fx`, `fy`, `ppx`, `ppy`, distortion
  `model` and `coeffs`. Only none/Brown-Conrady is currently supported.
- `thresholds`: positive `translation_m`, `rotation_rad`, `reprojection_px`;
  optional `rotation_span_rad` and `minimum_axis_ratio` control observability.
  These must be chosen for the experiment; software does not claim lab accuracy.
- `detection_limits`: `sharpness`, `coverage`, `reprojection_px`,
  `ambiguity_gap_px`, and optional `corners` (default 8).
- `observations`: at least six `training` and three independent `validation`
  entries, each with `pose_id`, `split`, `T_base_flange` (4x4), and a relative
  lossless PNG `image` path within the input directory.

`T_A_B` maps coordinates from B into A. `T_base_flange` must be actual observed
flange pose. Current UR readback reports TCP; its verified flange-to-TCP offset
must be removed before constructing this input. Rotation-vector values from UR
are not Euler angles. Do not substitute a target command for actual readback.

Image observations are redetected with OpenCV. Simulated geometry fixtures may
instead supply `T_camera_board` and `reprojection_px`; this alternate input is
rejected for a physical setup. Both branches retain their simulation flag.
The wrist role solves `T_flange_camera`; third views solve `T_base_camera`.

A completed bundle contains the canonical input, copied PNG evidence, corner
observations, solver settings, held-out residuals and a content-identified result.
Activation rechecks evidence and recomputes the solution, then copies one camera's
result into the matching station setup. Partial calibration is represented by
exactly the available camera entries. No absent camera result is synthesized.

Changing setup later cannot modify old episode snapshots or result bundles.
Invalid identities, changed optics, corrupted evidence, failed solve and failed
configuration replacement reject activation. A failed new bundle remains partial
or is never created; existing destinations are not overwritten. Station writers
serialize updates with a local advisory lock and preserve prior visible bytes
when replacement or directory synchronization fails. Power-loss behavior on the
actual station filesystem still requires deployment acceptance.

## Current GELLO assembly direction revision

Use [gello.calibration-20260912.json](../../config/gello.calibration-20260912.json)
for the current assembly's next mainline calibration binding. The operator
reported J2/J3 reversed; their signs are now +1/-1 respectively, giving
`[1,1,-1,1,1,1]` in motor ID order. All other calibration values are retained.
This revision supersedes the earlier rehearsal direction candidates, without
changing historical recordings or automatically activating any station.

```bash
ur-collect calibrate leader-validate config/gello.calibration-20260912.json
```

Use the existing `leader-activate` workflow with the matching original evidence
and declared lab assembly when syncing the station. Input-range/powered-motion
acceptance remains separate; see the [M12 correction record](plan.md#j2j3-direction-correction-2026-09-12).
