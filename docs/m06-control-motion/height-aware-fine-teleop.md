# M06: Height-aware Fine Teleoperation

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / acceptance pending, 2026-10-07. The user approved the concrete plan, candidate
correction settings, deployment and Isaac testing with generated leader input.
Physical robot control and leader motor writes are outside this run. Software
and simulation results will be recorded below; physical acceptance is NOT RUN.
Dependencies: M03 pose feedback, M04 relative leader mapping, M06 conditioning,
M10 recorded intent/command semantics and independent audit, M14 simulation.

## Confirmed requirements

- Near the working surface, reduce new leader displacement, following velocity
  limits and acceleration limits to 0.5 of their normal values.
- Use a continuous transition, with linear interpolation requested by the user.
  Do not insert a stop, settling wait or reference-reset pause at the boundary.
  Returning upward must also be continuous and must not restore old targets.
- Use the existing engineering surface reference with gain knots at +7 cm
  (1.0), +5 cm (0.75), and +3.5 cm (0.5). These replace the earlier +6/+4/+2 cm
  proposal. Preserve all three values through two linear segments.
- Address pending target displacement as well as new input gain. Lowering speed
  alone must not turn existing lag into a long, slow catch-up movement.
- The user approved combining gain scheduling, continuous incremental mapping
  and pending-target feedback correction. This includes the stated tradeoff of
  compressing excessive unexecuted travel; numerical correction settings still
  require simulation and alignment before production use.

"Half the target" means half the new leader displacement, not half an absolute
joint angle or all displacement since episode start. The proposed scope is all
six joint-space deltas; gripper mapping and HOME remain unchanged. This does not
assert that Cartesian TCP speed or acceleration is exactly halved.

## Height evidence and adopted engineering reference

The sibling `ur12e-training-infer` repository's TI07 plan and
`docs/checks/protection-history-z-20261006.json` contain:

| Historical quantity | Value / basis |
| --- | --- |
| Minimum nominal FK Z | 159.352649 mm; nominal URDF world-to-flange chain |
| Minimum recorded pose-proxy Z | 160.909951 mm; active-TCP proxy |
| Adopted lower bound | 154 mm; historical FK minimum minus at least 5 mm |
| Recorded proxy minus FK Z | 1.496361 to 1.777303 mm in the scanned dataset |

TI07 explicitly describes 154 mm as an operating bound, **not a measured table
height**. It cannot silently become a measured-TCP tabletop value here. Its
historical offset distribution also does not establish a fixed FK/TCP conversion
for every future pose. These findings come from local source inspection, not a
new hardware measurement.

The user's decision rule is to subtract 5 mm if the value is a historical
extreme, but retain it if that margin was already applied. Here the historical
extreme is 159.352649 mm and the margin is already included in 154 mm. Therefore
adopt **z_reference = 0.154 m**, without subtracting another 5 mm. Call it the
engineering surface reference, not a measured geometric tabletop.

Use the same nominal FK on fresh measured follower joints for both UR
and Isaac. Pin URDF SHA256
`51d3a3812a81c2a3d0ff2423a0aaab7c7547c19019297daba865a3c4bb04dd60`.
Preload the six-joint chain once from a configured/mounted asset; do not import
the training repository at runtime or hardcode a sibling checkout path. Existing
UR and Isaac feedback already supplies joints, so no new TCP protocol field or
robot connection is needed. Do not compare this reference with raw RTDE TCP or
Isaac scene-world Z (which also includes the workcell/base mounting).

The station declares zero active TCP, so its returned TCP coincides with flange
under that installation. The 127-mm physical tool offset remains metadata and
is not part of the adopted nominal root-to-flange reference. Changing the
installation, tool or surface requires checking that the baseline still
applies. If a physical tool point is later
chosen, rotate its local offset before comparing base-z; do not subtract a
constant 127 mm from base-z for arbitrary orientations. See
[M10 TCP semantics](../m10-data-contract/plan.md#tcp-installation-and-hand-e-timing-clarification-2026-09-13).

## Implemented algorithm composition

### 1. Continuous gain scheduling

Let `h = z - 0.154`, with z using the pinned nominal FK reference above.
The aligned knots require **piecewise linear** interpolation, not one straight
line: 5 cm is not the midpoint of 3.5 and 7 cm.

```
gain = 0.5                              if h <= 0.035
gain = 0.5 + 0.25 * (h - 0.035) / 0.015 if 0.035 < h < 0.050
gain = 0.75 + 0.25 * (h - 0.050) / 0.020 if 0.050 <= h < 0.070
gain = 1.0                              if h >= 0.070
```

| Relative height | Absolute nominal FK Z | Gain |
| --- | --- | --- |
| At or above +7 cm | At or above 224 mm | 1.0 |
| +5 cm | 204 mm | 0.75 |
| At or below +3.5 cm | At or below 189 mm | 0.5 |

Ascending uses the same curve; small height noise produces small gain changes
rather than mode toggles. These knots define the requested schedule, not a
validated physical clearance or braking margin.

Apply this gain to new input and the nominal following speed/acceleration caps.
For the present 24 deg/s and 30 deg/s2 profile, full fine operation requests
12 deg/s and 15 deg/s2, with existing conditioner headroom retained.
The current velocity cannot instantly obey a newly lower speed cap: preserve
command state and decelerate within the agreed acceleration envelope. Audit the
transition envelope explicitly; do not label finite braking a cap failure or
claim the new cap is achieved instantly.

[Gain scheduling](https://www.mathworks.com/help/slcontrol/ug/pidgainscheduler.html)
is an established way to interpolate parameters with an operating variable.
Here the scheduled parameters are mapping gain and motion caps, not PID gains.
Piecewise linear interpolation is continuous but has slope corners at its
knots. Retain the requested linear schedule and acceleration-limited command
state; do not silently substitute a cubic or claim a new jerk guarantee.

### 2. Incremental mapping and continuous command state

Before pending-target correction, update the reference from each fresh leader
sample exactly once:

```
reference_candidate = reference_previous + gain * signed_scaled(leader_delta)
```

Do not recompute `HOME + gain * all_episode_displacement`. That expression moves
the target when gain changes even if the leader is stationary. Preserve the
conditioner's command position and velocity through the entire transition.
This applies the principle of
[bumpless transfer](https://www.mathworks.com/help/simulink/slref/bumpless-control-transfer-between-manual-and-pid-control.html):
keep controller state compatible with the signal already being executed.

With variable gain, mapping becomes path-dependent. Returning to normal gain
does not repay movement attenuated in the fine zone. The existing immutable
episode-baseline reconstruction must therefore be extended explicitly in M10.
Gain scheduling alone adds no movement without new leader input; pending-target
correction below is a separate, recorded operation.

### 3. Bounded pending targets, inspired by tracking anti-windup

Gain interpolation does not erase a pre-existing target lead. Propose limiting
how far the accepted reference can run ahead of the conditioned command, then
continuously reducing excess lead with bounded correction. Preserve ordinary
gain mapping inside that allowance. Carry the corrected reference forward so
discarded excess cannot reappear when the arm rises out of the zone.

This adapts
[tracking anti-windup / back-calculation](https://www.mathworks.com/help/simulink/slref/anti-windup-control-using-a-pid-controller.html),
which feeds actuator limitations back into accumulated controller state. Our
accumulator is a position reference, not a PID integral; this is a proposed
adaptation, not a directly validated PID remedy. Related
[reference-governor methods](https://merl.com/publications/docs/TR2014-119.pdf)
modify requests ahead of an existing constrained controller. A full predictive
governor is not proposed for the first implementation.

The correction must account for current velocity and braking distance. Simply
pulling the target behind the stopping point can create overshoot and reversal.
Do not force a recoil solely because the gain changed, reset velocity to zero,
or continuously rebase to measured joints to hide a real tracking fault.
Leader reversal must remain responsive without replaying obsolete forward lag.

The agreed composition permits compressing excessive unexecuted travel.
Preserving every requested displacement instead requires allowing the follower
time to finish it; no interpolation guarantees both. Never restore compressed
travel on upward exit or reinterpret actual tracking errors as input debt.

Candidate correction details for offline/Isaac evaluation, not deployed values:

- Use a nominal lead allowance of `scheduled_speed * lead_seconds`, initially
  `lead_seconds = 0.20 s`. This is an angular allowance, not a promise that all
  motion stops or catches up in 0.20 s.
- Extend that interval to contain the current command's braking point. Account
  for the lowest acceleration that can apply during the transition and the
  actual conditioner behavior; do not rely on a constant-speed approximation.
- Project the candidate reference into this feasible interval, then move the
  reference toward the projection by `beta = 1 - exp(-dt / correction_seconds)`,
  initially `correction_seconds = 0.20 s`. Apply correction at control cadence;
  apply each leader increment only once. Bound and record all corrections.
- This is a soft contraction: it does not instantly enforce the final lead
  allowance. Existing hard lag, raw-jump and joint-limit checks remain active.
  Check the uncorrected candidate before contraction so an invalid request is
  not made admissible solely by compression.

Validate the feasible interval and the combination with the conditioner before
freezing these settings. Failure to maintain a continuous admissible command
uses the existing fault/stop path; the precision transition itself has no pause.

### Alternatives considered

[Ruckig](https://docs.ruckig.com/) provides online trajectories with velocity,
acceleration and jerk constraints. Its
[tracking interface](https://docs.ruckig.com/tutorial.html) addresses moving
targets and is a Pro feature. A trajectory generator alone does not decide
whether obsolete requested displacement should be retained. Defer this dependency
and a new jerk policy; first evaluate the existing conditioner with the above
reference management. Do not claim existing acceleration limiting bounds jerk.

## Integration and decisions before implementation

Keep one mapping/conditioning path and the existing device owner. Reuse fresh
pose feedback; no extra robot polling connection. Raw-input validity, joint
limits, command-to-measured tracking faults, stale-state handling and stop
supervision remain independent. This feature is precision assistance, not a
contact detector or a guarantee of collision clearance.

Preserve raw leader input, gain-scaled candidate, pending-target correction,
accepted reference, sent command and measured feedback as distinct auditable
quantities. Record height basis/configuration, fresh pose/sample identities and
applied gains/limits without fabricating acquisition samples. A compact recorded
contract must let M10 reconstruct the time-varying mapping and command limits.

Implemented scope: use the pinned FK basis above, bounded pending-target
correction and the six-joint scope with unchanged gripper/HOME.
Initialization inside the band uses its current gain and creates no historical
motion debt. Numerical correction settings are candidate test settings, not
physical commissioning acceptance.

## Estimated implementation size

Approximate added/changed Python lines, excluding documentation, generated
assets and dependencies; this is a planning range, not a code-volume target:

| Work | Estimated lines |
| --- | --- |
| Gain schedule, incremental reference and correction/conditioner changes | 90-150 |
| Pinned nominal FK loading/evaluation | 100-140 |
| Configuration, shared feedback integration, recorded contract and audit | 120-210 |
| Regression cases, recorded-input replay and Isaac acceptance harness | 300-500 |

Allow roughly **300-500 production lines plus 300-500 test lines**. The numerical
algorithm alone is smaller; recording provenance and independent verification
are part of mainline completion. Reuse existing native follower transport,
controller ownership and physics adapter. No Ruckig/MATLAB dependency or new
general control framework is planned. Isaac remains external to the collector
image; the collector image will need a cached source-layer rebuild at delivery.

## Isaac feasibility and proposed run

Read-only inspection on 2026-10-07 confirmed `ssh ur12e-collection` resolves to
`ur12e-flexlab`, with an RTX 2000 Ada (16,380 MiB), installed Isaac Sim 6.0.1.0,
scene repository revision `88fdf50`, the existing `runtime/physical.py` adapter,
and the same URDF SHA256 as the historical reference. No Isaac/teleop process
was found at inspection; no simulator or physical device was started. Resource
availability and performance must be rechecked at the actual run.

The collector already supports headless physical execution, 240 Hz physics and
solver joint/velocity feedback. Use this native follower and the exact mainline
mapper/conditioner, with recorded or synthetic leader input confined to tests.
The acceptance profile must use the physical collection limits (24 deg/s and
30 deg/s2), rather than the faster existing Isaac example limits. Reuse scene
paths through configuration/mounts, with a separate endpoint and artifact path.

1. Run deterministic numeric tests of knots, increment consumption, correction,
   derivatives and independent record reconstruction.
2. Run headless physical-drive Isaac with 120 Hz target production and 240 Hz
   solver steps. Use fresh solver joints for the same nominal-FK height signal.
   Verify feedback cadence and clock progression instead of fabricating RTDE
   timing. Do not use repeated kinematic placement as dynamics evidence.
3. Replay slow descent/ascent, repeated boundary crossings, stationary leader
   with old lag, rapid reversal, fast descent and combined six-axis motion.
   Compare correction disabled/enabled; record gain, candidate/corrected/sent
   targets, measured joints, lag, reversal delay and residual travel.
4. Exercise source loss, stale feedback, stop and session boundaries. Confirm
   that gain recovery never replays old movement and a new interval resets the
   mapping only through the existing engagement flow.

No monitor, physical leader, cameras or robot connection is required for this
algorithm acceptance. Actual camera-load/MCAP session testing is a later gate;
the existing Isaac physical follower does not implement camera capture and must
not be presented as a complete simulated recording rig. Simulation can validate
the software and its modeled dynamics, not real contact forces or physical
clearance. Physical enablement remains a separate operator-controlled step.

## Implementation sequence and acceptance

After alignment: freeze the height and reference contract; implement the shared
mapping/conditioner and its audit; test offline; validate in simulation; then
perform separately authorized physical acceptance. No planned boundary pause.

- M06-A03/M04-A03: 1.0/0.75/0.5 incremental gains; no command-position/velocity
  jump, gain-only historical target jump or repayment on upward exit; bounded
  accumulated lead, braking and reversal; unchanged ordinary mapping when the
  lead allowance is not exceeded.
- M06-A03/M06-A04: noisy heights, repeated crossings, stationary leader with
  existing lag, start inside the band, fast approach, gain decrease while moving,
  stale/nonfinite pose, reference mismatch and unchanged stop/fault behavior.
- M10-A01/A03: independent reconstruction of gain, corrected reference and
  command derivatives; detect missing/forged correction and limit history.
- M14: compare candidate behavior on recorded leader traces and simulation,
  including old lag on entry and immediate leader reversal. Measure residual
  travel, response delay and command derivatives; do not infer physical
  clearance from a simulated pass.

## Implementation and deployment

The shared `leader.Input` owns the continuous reference; `control.precision`
provides scheduling/correction and `control.kinematics` preloads the pinned
geometry. `leader.precision_audit` independently reconstructs the reference and
command rather than calling the runtime correction/conditioner. Existing owners,
raw plausibility/lag guards, measured tracking checks, gripper behavior, HOME and
stop thresholds remain unchanged. The per-cycle computation reads cached actual
feedback and performs no extra device I/O.

Add the object from `config/precision.example.json` as the top-level `precision`
object in an explicitly selected teleop config. The URDF path resolves relative
to that config; the launcher mounts the asset read-only. NumPy must be available
in the host launcher and image; this station already has host NumPy 1.26.4 and
the collector's pinned runtime dependency. Removing the object restores the
ordinary episode-relative path. No physical station configuration was enabled
in this run.

The PC candidate `ur12e-collection:precision-20261007` was built from the already
installed `current` image with `--pull=false --network=none` and a local wheel
installed using `--no-index --no-deps`. No base layers or dependencies were
redownloaded. Installed package bytes match all 125 source/schema files. Identity:

- Parent checkout: `1e63ca6` plus this reviewed, uncommitted feature patch.
- Package-tree SHA256: `3a6d0f700a9d0201129551c8ecd81c488c2f8db50d27d23a2b83dcd2fd685c9c`.
- Candidate image ID: `sha256:1f6f6041f226c3d17ac367f95af365ec05f95807970d178ba91381e8e5673604`.
- Existing `current` / production checkout `dfa83f8` remain selected.
- Isaac remains in its own installed environment and scene repository.
- Test clients use `--network none`, no USB devices and only the private Unix
  socket/scene mounts. All leader samples are generated in
  `tests/simulation/precision.py`; no physical robot/leader was contacted.

## Acceptance results, 2026-10-07

Software: local complete regression **793 passed, 5 skipped**; Ubuntu installed
candidate with ROS Jazzy **796 passed, 2 skipped**. An additional fast-gain-drop
regression subsequently passed in both environments; the final focused precision
suite contains **34 passing cases**. Black and Pylint passed. Initial Mac shared-
memory test failures were sandbox permissions and passed outside that sandbox.
The first Ubuntu ROS test invocation lacked writable `ROS_LOG_DIR`; rerunning
with `/tmp/ros-log` passed the complete suite without a source change.

M06-A03/M04-A03 and M10-A01/A03 software: **PASS** for the three exact knots,
continuous interpolation, incremental/repeated sample handling, no gain-only
movement or restored travel, acceleration-bounded speed-cap transitions, debt
contraction, original raw-jump/lag/joint/epoch rejection, stale feedback rejection,
independent reconstruction/forgery detection, interval reset, and synthetic MCAP
write/read/verify. No new topics or normalized gripper actions are introduced.

### Isaac results and limits

See the compact [acceptance receipt](height-precision-20261007.json).
Full logs, configs, raw generated acquisitions, actual solver feedback and
per-command audit evidence are retained in `artifacts/precision-20261007/` and
the PC candidate directory `~/ur12e-candidates/precision-20261007/`.

| 24-second physical-drive comparison | Correction enabled | Correction disabled |
| --- | --- | --- |
| Independently verified commands | 2,850 | 2,853 |
| Command rate | 118.76 Hz | 118.88 Hz |
| Gain coverage | 0.5 to 1.0 | 0.5 to 1.0 |
| Maximum pending target distance | 0.16633 rad | 0.26552 rad |
| Base residual travel after leader pause, 2.3-5 s | 0.13302 rad (7.62 deg) | 0.23176 rad (13.28 deg) |
| Base command reversal delay | 22.76 ms | 21.71 ms |
| Uncommanded base recoil before reversal | None | None |

M14 / M06-A03 algorithm comparison: **PASS** for both complete trajectories,
repeated descent/ascent, all gain regions, multi-axis input, accumulated lead and
reversal. Pending-travel correction reduced the measured base residual travel
by **42.6%** in this fixture. These are representative modeled results, not
statistical guarantees or proof of physical contact safety. The measured mapping
P99 in the comparison run with contraction effectively disabled was 0.203 ms;
the observed complete control cycle maximum was 10.17 ms. No exact 120-Hz
hard-real-time guarantee is claimed.

M06-A04 fault rejection: **PASS** in separate Isaac runs that froze generated
leader acquisitions or the feedback passed into height mapping. Both reject
within the existing freshness policy, terminate input ownership, and leave the
simulator with `active=false`, `owner=null`. This establishes revocation, not
strict physical standstill.

Strict stop/hold acceptance: **BLOCKED**. The existing legacy M14 force-drive
adapter reports nonzero solver velocity even at nearly stationary positions.
The first run could not engage at the real 0.01 deg/s threshold. Subsequent
isolated fixtures use the already documented M14 engagement tolerance of
0.01 rad/s, while keeping the shared real stop gate unchanged. The completed
enabled run timed out at 4 seconds with maximum reported speed 0.01407 rad/s;
it is not marked fully passed. The disabled comparison completed motion but its
finite simulator lifetime ended during stop supervision; no successful stop is
claimed for that run either.

An earlier, deeper trajectory triggered the actual-speed guard near nominal
z=0.158 m with finger-state disturbances. Contact was not independently measured.
That failure is retained, and the final trajectory reduces shoulder excursion
while still covering the complete gain band. Two simulator startup attempts also
timed out and were terminated without a client or hardware connection. None of
these outcomes changes physical safety gates or is relabeled as a passed run.

Physical robot acceptance and full live-camera MCAP collection: **NOT RUN**.
Keep the production profile disabled until its operator-controlled acceptance.
Strict modeled stop/hold requires separate work on the existing M14 dynamics /
drive adapter; do not loosen the real gate to accommodate that model. Before
physical enablement, confirm the nominal-FK reference for the actual station and
run the ordinary operator-controlled session with the explicit precision config.

### Reproducing a private simulator run

From the candidate source tree on Ubuntu, prepare a new output directory with
the existing Isaac Python and an explicit `--scene-root`. Run the ordinary
`scripts/isaac_follower.py` against the generated config, then execute
`tests/simulation/precision.py run --output <same-directory>` in the candidate
image. Mount that directory at the same path and the scene read-only; use
`--network none` and no devices. `prepare --no-correction` provides the A/B
baseline. `run --fault leader` and `run --fault feedback` inject a fault after
eight seconds. Use fresh server instances and start the client promptly so the
configured server lifetime covers the full trajectory plus stop observation.
Reports keep component results separate and return nonzero when full acceptance
is not established, including the known strict-stop model limitation.

## Continued debugging scope, aligned 2026-10-07

The user permits less strict operator-response acceptance for leader pauses and
reversals, full use of the available simulator host, and longer simulation runs.
Do not skip edge cases. This does not change real robot motion, tracking, raw
input or stop/fault limits. Physical control remains outside this work.

1. Diagnose the modeled hold discrepancy with synchronized position/velocity
   evidence and gravity-compensation comparison in the existing scene adapter.
   Preserve real solver feedback; do not replace it with zeros or silently
   switch to kinematic motion. Keep contacts and gravity enabled.
2. Make simulator lifecycle cover readiness, motion, stop observation and
   ownership release. Reuse phase-preserving scheduling rather than accumulating
   sleep drift. Keep all results and capture the terminal offending sample.
3. Add long pauses, reversal with substantial pending travel, deep approach,
   repeated/noisy height crossings, multi-axis input, source loss, stale feedback,
   reset and hard-limit cases. Repeat comparison trajectories from fresh models.
4. Accept bounded temporary acceleration/catch-up after a leader pause. Evaluate
   convergence over a conservative braking-plus-settling window; do not demand
   instant stopping or instant reversal. Require bounded command derivatives,
   eventual zero command velocity, no unrequested oscillation/repayment, and
   prompt rejection of invalid input. Keep pause/reversal behavior distinct from
   an explicit operator stop or fault, whose existing gates remain unchanged.
5. Record actual contact evidence for the original deep-approach failure and
   independently check arm/tool/table transforms. Do not treat a shorter test
   trajectory or a changed guard threshold as resolution of the failed case.

The current 0.20-second reference parameters and height schedule remain the
baseline. Adjust mapping only if the expanded evidence identifies a concrete
failure under these aligned acceptance criteria. Update M06/M14 acceptance with
actual results, including unresolved model limits and unrun physical checks.


## Departure checkpoint, 2026-10-07

Status: **implemented / simulator fault-profile and physical acceptance pending**.
The user requested ending this iteration before leaving the Isaac device. No
additional experiments were started after that request. This section supersedes
the earlier model diagnosis without changing its historical results.

### Corrections and software acceptance

The native scene put the articulation root on a rigid body, making a floating
articulation constrained by an external world joint. Moving the root API to that
world fixed joint produces an actual fixed-base articulation: eight generalized
joint DOFs instead of fourteen including the floating base. The root-only
stationary probe reaches 1.19e-5 rad/s maximum terminal speed. This topology
correction is present in the independent scene repository; its seven static
OpenUSD tests pass. Source assets and real robot configuration are unchanged.

M14 hold/release now preserves an already captured hold target. Repeated release
previously reseeded the target from gravity-deflected actual joints and caused
another sag after stop confirmation. New ownership explicitly reseeds the hold.
The physics loop also preserves scheduling phase, skips expired slots without
bursts, and reports healthy active feedback without an inactive-owner error.

M06-A03/A04, M04-A03, M10-A01/A03 and M14-A01 software: **PASS**.
Expanded cases cover both reversal directions at four heights, noisy knot
crossings with irregular time steps, stale/future feedback, interval reset,
existing hard limits and repeated loaded hold/release. Local complete suite:
**808 passed, 5 skipped**. Ubuntu installed image with Jazzy: **811 passed,
2 skipped**. Focused precision: **47 passed**. Black and Pylint (10.00/10) pass.
The first Ubuntu invocation lacked writable ROS logging; the complete rerun
with `ROS_LOG_DIR=/tmp/ros-log` passed without a source change.

### Physical-solver evidence

All inputs were synthetic. Real solver positions, velocities, contact impulses
and transforms were recorded; gravity, table contacts and self-collision remain
enabled. The real 0.01 deg/s, 200 ms sustained stop gate and four-second budget
were not relaxed. Each completed run also checks ownership release and observes
approximately three seconds of subsequent hold. Fresh instances have a
300-second lifetime and explicit cleanup.

| Exact experimental configuration | Cases and conclusion |
| --- | --- |
| Fixed root, PGS, original force drive | Stationary and nominal stop pass; deep contact stop fails. Increasing iterations does not resolve it. |
| Fixed root, TGS 240 Hz, gravity feedforward, 16 position / 4 velocity iterations | Sweep with/without correction, reversal and noise pass including strict stop and post-release hold. Deep contact rejection passes in a repeat. Leader/feedback-loss rejection works, but strict stop fails. |
| Same compensated TGS, external forces every iteration, 16 / 0 | Deep trajectory completes with contacts and strict stop; leader-loss stop still fails. Completion is not collision-safety acceptance. |
| Same compensated TGS, external forces every iteration, **4 / 0** | Final `leader-loss-p4v0` run passes stale-input rejection, strict stop in **0.498 s**, ownership release and post-release hold. All other cases on this exact profile are **NOT RUN**. |

NVIDIA documents [nonzero steady-state articulation velocity with TGS](https://docs.omniverse.nvidia.com/kit/docs/omni_physics/110.0/dev_guide/guides/current_limitations.html).
Its suggested external-force setting alone did not resolve our fault poses.
More resources, 480 Hz and higher iteration counts also failed. The last profile
is an experimental candidate, not a selected production solver configuration.
Gravity feedforward and solver changes are retained only in diagnostic adapters;
the scene runtime contains only the verified fixed-root correction. Feedforward
plus PD drive limits do not establish a physical UR torque/safety model.

The expanded same-model A/B comparison at about 120 Hz reduces residual base
travel after leader pause from 20.07 to 12.71 degrees (**36.7%**). Command velocity
settles after 2.15 versus 1.61 seconds. Early reversal while 13.19 / 18.69 degrees
remain pending takes 0.575 / 0.783 seconds to reverse command direction. These
bounded catch-up intervals satisfy the relaxed response expectation; they are
not instant stopping. The 0.20-second mapping parameters remain unchanged.

Deep-approach contact impulses correlate with the speed-guard rejection. The
independent measured flange/base transforms agree with nominal FK to less than
0.7 micrometers in the recorded noise/deep checks. This excludes a root/frame
translation mistake in the height schedule; neither the 154 mm reference nor
the fine-motion mapping guarantees contact avoidance.

### Saved state and next action

The complete evidence archive is copied to
`artifacts/precision-20261007/debug/checkpoint.tar.gz` on Mac, with extracted
runs under `artifacts/precision-20261007/debug/evidence/`. PC originals remain in
`~/ur12e-candidates/precision-debug-20261007/`. The linked JSON receipt records
archive checksum, per-run reports and the exact candidate adapter hashes.

The offline-built PC image is `ur12e-collection:precision-debug-20261007`, ID
`sha256:19e05e67923be1b01c8d1a602a6fb5af2d56c3e71b931c4d34b4e21a93c79b34`.
Its package-tree SHA256 is
`23df5c2bffbd14d9de5c9e0f7bdf88a238d0f94d4785270eac22a039cf161818`.
Production `current` still selects `dfa83f8`; precision is not enabled there.
Isaac test processes are stopped. Existing unrelated URSim is left running.

Next Isaac visit: use **one exact 4 / 0 candidate** for sweep and A/B, reversal,
noise, feedback loss, original deep approach and repeated leader loss. Require
all unchanged strict stop/hold gates before selecting a solver profile. Do not
combine passes from different configurations into complete acceptance. Physical
robot and live-camera recording acceptance remain **NOT RUN**. No production
switch, commit or push is part of this departure checkpoint.

## Ordinary GELLO configuration, aligned 2026-10-07

The user requests moving to operator-run physical evaluation and making this
algorithm selectable in the ordinary `ur12e gello` configuration. Remaining
Isaac solver/contact regression is a separate model gate, not a requirement to
keep iterating that model before physical evaluation. Physical acceptance still
requires its own evidence; simulator results do not replace it.

Implementation scope: add Boolean `precision.enabled`, enable the repository UR
profile, and retain the identical ordinary relative mapping when false. Omitted
precision continues to mean simple teleoperation for existing station profiles.
Read this setting once per launch, never switch mappings within an episode.
Bundle the exact pinned nominal URDF and its license under `config/kinematics/`
so the collector does not require an Isaac checkout. Display the effective mode
and selected configuration before hardware access. Existing station-local
configuration precedence, motion/stop guards, gripper and HOME remain unchanged.

Acceptance: validate enabled/default/disabled configuration; disabled mode must
not read the URDF or add height-feedback requirements, incremental mapping or
pending-target correction. Compare its command and interval metadata to an
ordinary no-precision input. Validate Boolean types and reject an invalid
active asset. Run software regression and formatting/lint. No physical control,
PC deployment, image promotion, commit or push is part of this configuration
increment. A later station deployment must explicitly update any local override.

Configuration increment results: **PASS**, 2026-10-07. The default UR profile
loads the bundled hash-pinned asset from an isolated copied configuration tree;
no sibling repository is needed. `precision.enabled=false` returns no profile
before asset access, and produces identical commands/context to an omitted
precision profile through forward and reverse input. Non-Boolean switches and
corrupted active-asset hashes are rejected before hardware access. The focused
configuration/physical/entrypoint suite passes **163 tests**; the final local
complete suite passes **815 tests, 5 skipped**. Black and Pylint pass. Five Mac
shared-memory tests initially failed under sandbox restrictions; the full
hardware-free suite passed outside the sandbox without a test or runtime fix.

Ubuntu image rebuild, station-local profile migration, physical operation and
recording with this feature: **NOT RUN** in this increment. The previous
candidate-image identity does not include these new configuration changes. The
existing production image and station profile remain unchanged. On delivery,
copy the enabled precision object into the selected station profile, using
`../kinematics/ur12e.urdf` for `config/local/teleop.ur.json`; do not overwrite
station identities, calibration, device paths or motion parameters.

## Repository delivery, 2026-10-09

The user authorized committing and pushing the completed collection changes to
remote `main`. The PC is unavailable; no connection or deployment is attempted.
This delivery retains the recorded 815-pass local regression and explicit
physical/simulator acceptance limitations. No runtime behavior changed after
that regression. The deployed image and station-local configuration require a
separate update when the device is available.
