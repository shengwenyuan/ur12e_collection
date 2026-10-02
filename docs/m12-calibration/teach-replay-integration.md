# M12: Native 480p Teaching and Replay Integration

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: imported-route replay implemented / physical acceptance pending,
2026-10-03. Interactive teaching remains deferred for this increment.
Dependencies: M02 station configuration, M03 feedback, M06 motion ownership,
M07 cameras and M10 provenance. This extends
[the AprilGrid implementation plan](keyboard-aprilgrid.md) and supersedes its
high-resolution capture defaults and deferred teaching scope.

Replay timing update, 2026-10-03: the operator explicitly approved the
colleague's moveJ speed 0.15 rad/s and acceleration 0.30 rad/s², and shortened
the stationary capture window to 1.5 seconds. Apply these to calibration only;
collection HOME and teleoperation settings remain unchanged. Record the actual
capture duration in each new run and retain verification of historical
two-second runs. Update previews, boundary tests and deployed images without
launching hardware. This supersedes the two-second replay references below.

The operator also approved calibration-only stopJ deceleration 0.30 rad/s².
Explicit `--replay` authorizes motion without another approval flag. The mutually
exclusive `--validate` mode only reads configured routes or existing evidence:
alone it previews the route, with `--solve RUN` it writes a new derived bundle,
and with `--verify BUNDLE` it checks that bundle. It never connects to devices or
activates results. Keep `--activate BUNDLE` as a separate explicit operation.
Acceptance must cover missing/conflicting modes before device access, offline
input isolation, calibration-only rates and historical capture verification.

## Evidence and agreed scope

The colleague repository was reviewed at `7cd6dea`. The operator reports that
its extrinsics reproduce the real viewpoints in the digital twin with small
deviations. Treat this as preliminary support for the workflow and transform
results. It is not an independently measured millimeter accuracy result.
Reuse useful teaching, detection, diversity and reporting logic, adapting it
to this repository's device owners and data contracts rather than importing a
second control stack.

On 2026-10-03 the operator accepted the proposed teaching/replay entries,
independent held-out validation and actual TCP-offset conversion. Use the
original PDF as the default board assumption; its configuration can change
later without blocking software development. No hardware execution is
authorized by this planning update.

## Operator flow and configuration

The aligned complete workflow includes:

```sh
ur12e cali --left --teach
ur12e cali --left --replay
```

`--replay` is implemented; `--teach` remains a later increment. This deployment
uses the colleague's already measured teaching through the offline importer.

The same modes support `--right` and `--wrist`. Resolve station files, selected
routes and output roots from configuration; retain explicit path overrides.
Do not hard-code a checkout location or depend on the shell's working directory.

1. Teach bounded keyboard moves with a live image and board-quality/diversity
   feedback. Save actual joints, observations and route order at accepted stops.
   Reuse existing ownership, joint limits and stop handling. Joint jogging
   needs no IK; any Cartesian jogging must have a separately specified seeded
   IK and rejection contract before implementation.
2. Replay saved joint targets through `moveJ`, with no new IK or generated
   detours. Validate the complete route and starting conditions first. At each
   measured stable arrival, acquire a fresh two-second image/feedback window.
   The colleague's movement-only replay is not sufficient for this capture step.
3. Fit intrinsics, then extrinsics from the fresh run. Preserve independent
   validation poses selected before fitting. Report failures without silently
   relaxing thresholds or replacing the active calibration.

All three production camera roles remain configured and serial-bound:

| Colleague role | Collection role | Reference serial |
| --- | --- | --- |
| camera_1 | wrist | 260522273667 |
| camera_2 | third_left | 327122073926 |
| camera_3 | third_right | 327122075735 |

Serials belong in station configuration, not implementation constants. A run
may capture one selected camera; simultaneous visibility is unnecessary.
For fixed views, Hand-E holds the board rigidly. For the wrist view, the board
is fixed to the table. Calibration must not inherit collection HOME's automatic
gripper opening.

## Image, board and frame contracts

- Capture and detect native **640 x 480 RGB at 30 Hz**. No 720p detection followed
  by coordinate scaling. Keep the existing depth/stereo factory calibration.
  The colleague's current camera configuration already selects 480p, although
  historical comments and some intrinsic provenance refer to 720p.
- Do not silently copy blended intrinsic results that combine 480p fitting
  with old 720p distortion coefficients. Fit and validate the production mode;
  collect additional edge coverage/tilt if distortion is poorly constrained.
- Default to `aprilgrid_Letter_tag36h11_4x6_28mm_actual_size.pdf`, with its
  inspected geometry, hash and corner convention in the parent plan. Store
  dictionary, dimensions, spacing, ID layout, origin and marker orientation in
  a versioned board profile. The colleague's top-down OpenCV grid convention
  differs from this PDF's bottom-up, rotated-marker convention. Changing the
  profile must not reinterpret historical observations in place.
- Record actual TCP pose and the controller's active TCP offset. Derive
  `T_base_flange = T_base_tcp @ inverse(T_flange_tcp)` for the calibration
  solver. The physical 127 mm tool extension is not a substitute for that
  queried offset or the board attachment transform. Use meters, radians and
  explicit transform directions.
- Retain the existing 20-40 capture-checkpoint contract, at least 15 fitting
  and five independent held-out poses. A typical run uses 20 fit + 5 held-out.
  Neither intrinsic fitting nor sample selection may use held-out results to
  tune the solution. The colleague's final `all_30` result has no independent
  held-out set; its reported fit is supporting evidence only.

## Output and retained information

Default root: `~/ur12e-calibration/<role>/`, configurable at deployment.

```text
routes/<route-id>.json
runs/<run-id>/
results/<calibration-id>/
```

Use our JSON, lossless PNG, trace and incomplete-run conventions. Preserve the
colleague's information content without duplicating angle units/names or
adopting its directory layout:

- Role, serial, camera profile/intrinsics provenance, board/setup identity,
  route and checkpoint IDs, initial reference pose and software versions.
- Actual joints/velocities, TCP and active offset, robot/safety modes, source
  and host timestamps, measured settling duration and pose diversity.
- Raw images, detected IDs and corners, object/image points, board-pose
  estimates with their intrinsic provenance, blur/coverage/border/residual
  metrics, rejected observations and reasons, fit/validation membership.
- Fitted intrinsics/distortion, directed extrinsics, uncertainty and per-view
  validation, evidence hashes, diagnostic overlays and immutable result IDs.

The AprilGrid result bundle and older station activation schema currently
differ. The explicit `--activate` conversion now produces a schema-3 AprilGrid
station snapshot after full bundle verification; it does not relabel a
schema-1 ChArUco result. Failed verification
or mismatched camera/profile/board identities must preserve the prior result.

## Implementation order and acceptance

1. Add configured board/role/path contracts and explicit teach/replay modes.
2. Adapt teaching and quality feedback to shared motion/camera ownership;
   export measured joint routes and preserve raw teaching evidence.
3. Enforce native 480p replay, retain fresh two-second captures and separate
   fitting/validation; adapt reporting and station activation.
4. Run offline tests, then separately authorized supervised lab acceptance.

| Stable gate | Integration evidence required | Result |
| --- | --- | --- |
| M12-A01 | Imported measured joint routes and fresh stable two-second captures | PASS software; physical NOT RUN |
| M12-A02 | Role mappings; native 480p; PDF corner mapping; explicit invalid/insufficient-view rejection | PASS software; current visibility NOT RUN |
| M12-A03 | No held-out leakage; known fixed/wrist geometry; nonzero TCP offset; physical accuracy reported separately | PASS software; physical accuracy NOT RUN |
| M12-A04 | Interrupted runs retain evidence; failed solve/activation preserves prior calibration | PASS software |
| M06 / M10-A03 | Exclusive owner, bounded stop, no board release; clocks/units/transforms traceable | PASS device-double regression; physical NOT RUN |

Earlier replay/solver software acceptance remains recorded in the parent plan.
Current checks and delivery are recorded in [the Flexlab receipt](flexlab-replay-20261003.md).
Exact keyboard bindings
and step sizes remain implementation planning details before motion development.

## Approved deployment increment (2026-10-03)

The operator requested implementation and deployment using the colleague's
existing taught waypoints, avoiding another teaching session. Deliver the route
import/replay/solve path first; interactive keyboard teaching remains a later
increment. Import actual measured radians in recorded order, never old fitted
extrinsics or old images as fresh observations. Preserve the original source
file/hash next to the canonical route. Use the first waypoint as the required
start, avoiding an invented transit from the colleague's later redefined center.
Reserve every sixth checkpoint for validation before any new image acquisition
(25 fit + 5 validation for the supplied 30-point routes).

A configured `calibration.json` resolves role routes and output root; explicit
overrides remain available. Offline preview reports each segment's unwrapped
joint delta and nominal moveJ duration, start/end joints and existing speed/
acceleration bounds. It cannot establish collision clearance. Neither import,
preview, image deployment nor offline tests may send hardware commands. First
physical replay remains operator-launched and supervised. Deployment requires
confirmation of the intended SSH station because the alias currently differs
from the most recent delivery record.

## Repository review before publication (2026-10-03)

The existing collection tree at `d1895b2` is identical to `ee78221`; the reverted
container entrypoint is not restored by this integration plan. After refreshing
the remote, local main was six commits ahead with no divergence. Review covered
the final code changes and the intermediate reverted additions. A limited
credential-pattern check of all six commits' added lines found no matches;
this is not a comprehensive security audit.

Local Mac `scripts/check` completed: Black PASS (207 files), Pylint PASS
(10.00/10), pytest PASS (693 passed, five skipped). This validates the existing
offline software, not the planned integration or physical calibration. This
update changes documentation only; no image rebuild or hardware launch occurred.

## Replay/validation timing update acceptance (2026-10-03)

- M12-A01 / M06 PASS software: calibration-only moveJ 0.15 rad/s,
  acceleration and stopJ deceleration 0.30 rad/s²; stationary capture 1.5 s.
  Lifecycle tests verify the effective transport configuration and unchanged
  collection configuration. New runs preserve capture and stop timing.
- M12-A03/A04 PASS software: offline `--validate --solve` and `--verify` use
  real rendered-image evidence without opening device factories or changing
  raw input. Historical two-second runs still verify; incorrect dwell fails.
- M01-A03 PASS software: explicit `--replay` launches without an extra approval
  flag; missing/conflicting modes fail before network/device access. Offline
  host commands use the network-isolated image and read-only evidence mounts.
- Mac checks: Black PASS (213 files), Pylint PASS (10.00/10), pytest
  **717 passed, five skipped**. Image delivery results follow in the linked
  Flexlab receipt. Real camera capture and robot replay: **NOT RUN**.

Delivery completed on Mac and Flexlab: the installed Ubuntu image passed
720 tests with two skipped on each host; all 121 package files match source.
Both deployed offline validation entries and both 30-point synthetic-feedback
route traversals passed. See the current section of the Flexlab receipt for
image identity, preserved configuration and rollback. Hardware remains NOT RUN.
