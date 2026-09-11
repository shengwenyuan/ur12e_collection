# GELLO Hardware + URSim Follower Integration

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: ALIGNED / implementation started. Updated: 2026-09-11.
Primary module: M04. Related modules: M01/M02/M05/M06/M07/M08/M09/M10/M11/M13.
Alignment: the user approved S1-S6 on 2026-09-11. The subsequent review
supersedes strict absolute engagement with episode-relative joint deltas anchored
to verified follower HOME. Calibration and ambitious HOME/HOLD diagnosis remain
required; historical arrival errors are not accepted. Prior absolute-mapping
software tests below describe the previous implementation, not acceptance of the
new episode-relative behavior. Read-only hardware access is authorized. Every
motor register write still requires explicit confirmation.

## 1. Outcome and evidence boundary

Use the physical seven-motor leader with the existing local URSim follower,
three replayed lab RGB-D streams, and the production recording pipeline. Exercise
calibration, engagement, following, stopping, review, return, recording,
verification and export without accessing the physical UR12e.

The user reports the leader is connected and powered. Read-only diagnostics
are authorized; motor register writes need explicit confirmation. Power-on does not
establish torque state, cable clearance or holding acceptance. Subsequent leader
motion tests need a concrete aligned procedure and supported mechanism.

Inputs, retained unchanged and excluded from builds and Git:

- `/Users/shengwenyuan/Downloads/leader_arm_handover_20260911T005739Z`:
  complete colleague snapshot; 39 manifest entries verified in the prior read.
  Current configuration is seven XL430s, TTL Protocol 2.0, 57600 baud, shared
  12 V / 5 A supply. ID2 has an unresolved hold fault, ID3 automatic movement is
  disabled for cable clearance, and ID6 lacks a completed homing record.
  Its 33 software tests passed in an isolated container during this increment.
- `/Users/shengwenyuan/Downloads/ur12e-lab-replay-20260911`:
  two completed 30 s MCAPs and one incomplete failure fixture. Existing bundle
  verification reports full RGB decode and depth hashes; all input hashes were
  rechecked before caching. Never execute bundled historical physical launchers.
- Existing project implementation: M04 is an unavailable stub; URSim control,
  session ownership, native HOME, recording, stop confirmation and export exist.
  Reuse these implementations. Do not import the colleague's whole control loop
  or create a second production UR controller.

Current follower HOME remains `[0, -90, -90, -90, 90, 0]` degrees.
No physical UR/Hand-E control or new physical-camera acceptance is in scope.

## 2. Mapping decision

Define leader angle in UR joint coordinates, in radians:

`q_cal[i] = q_home[i] + sign[i] * ratio[i] * (raw[i] - raw_home[i]) * 2*pi/4096`

`raw` is signed, branch-preserving encoder feedback. `ratio=1` is the proposed
default for joint-angle copying, subject to the actual mechanical transmission.
Joint sign, reference, gear ratio, branch and bounds are explicit calibration.
Never take an absolute value of a joint angle or silently wrap it to +/-pi.

Current aligned control mapping, superseding the earlier absolute-only choice:

`q_target(t) = q_follower_HOME + q_cal(t) - q_cal(t0)`

`t0` is one fresh, stable leader reference captured at recording/leading start.
The follower must first be verified stationary at configured HOME. With fixed
signs/ratios and continuous encoder branches, the leader's calibration zero
cancels from the delta. Exact leader/follower HOME equality is not an engagement
requirement. Leader HOME remains useful for repeatable ergonomics, range and
powered-return diagnosis; its positioning accuracy remains a separate gate.

Each sample is compared directly with the immutable episode baseline. Never
integrate successive increments, accumulate the previous episode's target, or
refresh the baseline after dropout/reconnection. A new episode verifies follower
HOME and captures a new baseline. This prevents cross-episode offset accumulation
under those conditions. Absolute and relative mappings remain mathematically
different when their startup references differ; both can be valid designs for
this collector, whose training targets are follower states/commands.

Persist the mapping mode, raw/calibrated baseline, source timestamp/sequence,
calibration identity, configured follower HOME and actual follower startup state.
Retain raw leader state, mapped intent, bounded sent targets and actual follower
feedback separately. Gripper endpoints keep their existing absolute OPEN/CLOSED
mapping rather than inheriting arm episode deltas. Stale input, ambiguous
wrap/reset, invalid range or limit violations still reject control. No mid-episode
re-anchoring or HOME/HOLD tolerance relaxation is implied by this design.

Implementation scope approved on 2026-09-11: replace absolute-only engagement with
an immutable episode reference and source-epoch-aware mapping. Use at least three
stationary samples spanning 40 ms (<=2-count spread) for engagement, distinct from
the longer physical calibration reference capture. Check actual follower HOME,
velocity and feedback age using existing control limits; reject stale/reordered
leader samples, epoch changes and target bounds with a latched episode fault.
This increment stops before hardware configuration writes or follower commands.
Calibration records describe fixed joint coordinates; mapping mode and baseline
belong to episode context rather than changing the calibration on every start.
Acceptance must cover different leader starting angles across episodes, zero
initial delta, no accumulation, immutable baseline, restart invalidation and
bounded intent. Do not claim the existing strict-engagement tests accept this
revised behavior.

## 3. Calibration and HOME diagnosis

Leader joint calibration is a mainline M12 workflow alongside three-camera
calibration. M04 owns encoder/servo mechanics and M02 stores versioned results;
M12 supplies the common entrypoint and independent workflow/activation semantics.
Do not overwrite colleague calibration files or modify motor Homing Offset.

- Read motor identity, firmware, operating/drive modes, torque, encoder position,
  hardware limits, PID/profile/PWM settings and available health registers.
- Use a supported, repeatable physical reference corresponding to follower HOME.
  Visual resemblance alone is insufficient to establish all six axis zeros;
  retain the fixture/alignment method and residual uncertainty in the report.
- Sample a stable reference (candidate: 1 s, at least 30 independent samples,
  spread <=2 counts), then verify each axis with positive/negative operator
  movement at several points within its cleared range. Keep other axes fixed.
- Save names, IDs, serial adapter identity, signs, raw HOME, ratios, limits,
  branches, gripper OPEN/CLOSED, calibration version/hash and raw evidence.
  Retain raw counts, calibrated angles and corrected targets separately.
- Check an independent return and reverse approach. Separate encoder-reported
  error from external joint-angle repeatability, mechanical compliance and play.

The official encoder resolution is 4096 counts/rev (~0.088 degrees/count).
This is not an output-accuracy specification. The colleague's +/-20-count
arrival tolerance already permits ~1.76 degrees; it cannot diagnose why the
measured position differs from the goal. A 1-2 degree error alone proves neither
insufficient torque nor the impossibility of a better result.

Compare supported versus normal-load holding and both approach directions;
record commanded/measured position, velocity, PWM, voltage, temperature, errors
and time. Diagnose saturation, settling, configuration and mechanics before any
gain/profile/output change. No blind PID tuning, increased PWM, overload test,
automatic error clearing or removal of the ID3 motion block.

Accuracy investigation target: <=0.25 degree encoder-reported HOME error,
with external-angle repeatability measured independently. This is an ambitious
candidate target for diagnosis, not a guaranteed motor accuracy or permission to
relax other protections. The old +/-20-count threshold is historical only.
Record exact residuals over repeated approaches and a supported 30 s HOLD;
no compensation or tolerance relaxation is authorized if this target fails.

Current support reported by the user: the base plate is held under the Mac,
and the end motor rests on the desk; matching follower HOME requires assistance
by hand. Do not infer that this is a restrained motion fixture, a calibrated HOME,
or self-supporting holding. Before any motor write, obtain user confirmation for
the precise operation and affected axes; begin with read-only diagnosis.
Manual-support integration, if possible, never closes powered HOME/HOLD gates.

## 4. Ordered development and acceptance

| Stage | Modules / stable gates | Implementation and exit condition |
| --- | --- | --- |
| S1: isolated transport | M01/M02/M04-A01 | Rerun/import-review colleague tests; implement one serial owner with explicit open/close, immutable samples, health, sequence and clock provenance. Read all seven IDs; establish actual acquisition timing under torque-off operation. No implicit register writes on import/read. |
| S2: calibration and mapping | M02/M04-A03/M10-A03 | Implement the supported calibration workflow, signs/branches, gripper endpoints and episode-relative engagement. Test wrap/reset, invalid reference, unstable start, immutable baselines, no cross-episode accumulation and calibration round trip. Confirm each axis physically before follower motion. |
| S3: leader HOME/HOLD | M04-A02/A04, M06-A02 | Reuse reviewed motor primitives; add current-position HOLD and episode handovers. Test per-axis supported behavior before coordinated motion; retain partial-enable/ACK-loss accounting. No stale goal, automatic release on fault, or false holding success. If deferred, clearly label manual-support acceptance separately. |
| S4: real leader to URSim | M06-A01/A03/A04, M09-A01/A02 | Inject a real leader source into shared ownership/session logic. Preserve native follower HOME, limits, immediate stop and fault latch. First J1, then each axis, then combined/reversal/asymmetric paths within cleared leader bounds. Use recorded/synthetic targets for URSim-only extreme cases rather than forcing leader hardware toward limits. |
| S5: real-scene workload | M07/M08/M10/M11/M13-A01/A04 | Add disposable replay feeder, mixed-source provenance and resource instrumentation. Three RGB-D streams pass through matching and real re-encoding/writing. Historical follower data is never substituted for current URSim feedback. Compare isolated stages, combined load and finalization interference. |
| S6: integrated batch | M09-A01/A03/A04, M10-A01/A02/A03, M11, M13-A03 | After short and fault gates pass, run 20 x 40 s episodes with physical leader and URSim; exercise Space stop/review/return/restart, discard and Ctrl+C separately. Verify every file and one local export; publish exact passed slices and remaining hardware gates. |

S3 software and S5 can progress independently of physical motion approval.
Do not count manual support as successful automatic HOME or powered HOLD.
Stage-level results must remain separate from complete S6 acceptance.

## 5. Serial timing and control architecture

- Reject the current seven-by-83-byte bulk layout: at 57600 baud its payload
  alone needs ~101 ms, exceeding its 100 ms freshness policy.
- Prioritize a controlled 57600-to-1000000 baud migration on the existing U2D2;
  see [migration plan](baud-migration.md). Physical writes remain unapproved.
- Benchmark compact position/velocity reads and separate lower-rate health reads
  without changing motor configuration first. Preserve health age independently.
- Evaluate a compact indirect register map if needed; its setup writes must be
  explicit and read back. Evaluate a coordinated baud-rate migration only after
  adapter/cable verification, with saved settings and a recovery procedure.
  Neither configuration change is implied by a read-only probe.
- Candidate target: 100 fresh full-arm samples/s; minimum for the first full
  integration gate: 50/s, p99 sample gap <=40 ms, p99 acquisition-start-to-control
  age <=40 ms, no sample age/gap over 100 ms in steady operation. Report p50/p95/
  p99/max, errors and missing samples. These are proposed gates, not measurements.
- Preserve the existing 50 Hz URSim command loop initially. A higher command rate
  is a separate measured decision; never present 500 Hz commands as 500 Hz sensing.
- Use a latest-sample mailbox for control plus a separately bounded recording
  channel. Cached readings never receive new source timestamps/sequences.
  Camera, codec, disk and diagnostic work never block serial/control ownership.
- Map intent first; apply a bounded velocity/acceleration conditioner in the
  shared control layer, recording intent and actual sent targets separately.
  Test reversals, lag, stops and limit approach. No jerk guarantee is claimed
  until an explicit limiter and corresponding tests exist. Never extrapolate
  through stale input or suppress rate/limit failures to make the gate pass.
- Leader sample clocks originate on the Mac serial owner. A bridge must retain
  acquisition start/end, receive time, clock domain/epoch and measured uncertainty;
  calibrate the cross-process/VM mapping, bound transport delay and reject resets.
  Receiving an old packet must not make it fresh.

Mac proposal: native serial worker and a bounded local bridge to the container.
Ubuntu uses the same bus implementation with a direct device transport. Prove
the bridge path first; do not assume Docker Desktop exposes a Mac serial device
as a usable Linux `--device`. Retain the simulator's inspected identity, exclusive
lease and no-external-route boundary. Prefer host-initiated access to a restricted
ingress endpoint; validate Docker networking rather than weakening the boundary.
The bridge must not expose arbitrary register or physical-UR forwarding commands.

## 6. Replay fidelity and resource allocation

Observed evidence from this bundle:

- Two 30 s episodes: 898 and 899 accepted groups; 337,870,190 and 347,677,335 bytes
  (~11.26 and ~11.59 MB per capture second, decimal units).
- Writer queue peak 1; feedback queue peak 2; maximum queue delay 28.23/30.91 ms.
  Mean recorded group work is ~21.03/21.88 ms. No group p95 is in this summary.
- Supervisor peak RSS ~816 MiB is only that process. Host inventory was captured
  after recording, not during it. This package does not provide full historical
  CPU/GPU/disk utilization time series.
- Lab PC: Core Ultra 9 285, 24 logical CPUs, ~64 GB RAM, Ubuntu x86_64.
- Current Mac: Apple M5, 10 cores, 16 GB RAM. Docker Desktop 29.7.2 reports 10
  vCPUs and 8,319,504,384 bytes (~7.75 GiB). URSim has an existing 4 GiB cap;
  one idle-time sample was 1.43 GiB. This is not a measured peak under motion.

Replay procedure:

1. Verify source checksums and use completed recordings for normal input. Keep
   the partial recording exclusively as corruption/failure/recovery evidence.
2. Predecode RGB8/Z16 to a removable disk cache outside the timed benchmark;
   use bounded prefetch/mmap. Sixty seconds of three-view raw RGB-D is about
   8.29 GB, so do not preload it all into this 16 GB Mac.
3. Pace independent view deliveries from recorded acquisition/receipt offsets,
   with preserved source provenance and a new replay epoch. Send raw frames into
   the existing matcher, encoder and writer; copying encoded MCAP payloads does
   not test compression cost. Retain 16.7 ms skew and 75 ms matching/tail budget.
4. Only accepted image payloads were recorded; rejected/missing images and
   pre-alignment depth are unrecoverable. Test matching from retained per-view
   timestamps, and missing/late/wrap behavior with separately labelled injected
   fixtures. Do not claim reproduction of the original complete camera arrival
   stream, USB transport, exposure synchronization or RealSense alignment CPU.
5. Keep two modes: original 30 s timing for trace comparison; explicitly looped
   replay for 40 s episodes/batch. Rebase times monotonically at loop boundaries,
   preserve original frame IDs plus loop provenance, and never call repetitions
   new physical exposures. RGB is second-generation H.264 after re-encoding;
   depth pixels must match the input exactly.
6. Live leader, current URSim feedback and replay cameras need per-source origins
   (`physical`, `simulation`, `replay`) and clock metadata. A global simulated
   flag alone is insufficient. Historical UR/Hand-E feedback can run as a
   separately named workload fixture, never as current observations. Hand-E
   command mapping is testable; actual Hand-E feedback remains absent unless an
   explicit simulated server is used and labelled as such.

Process ownership: one native serial worker; one bounded bridge/control owner;
three persistent view feeders; one matcher/recorder owner; one ordered writer
with three H.264 contexts; an asynchronous finalizer; existing separate URSim.
Reuse existing shared-memory and lifecycle abstractions where applicable.

Initial memory budget candidates: existing URSim cap 4 GiB, collector including
feeders/finalizer 2.5 GiB, bridge/telemetry within remaining VM headroom. Keep raw
cache on disk. These are trial caps, not proven sufficient allocations. Start
without hard CPU quotas; measure startup/finalization bursts, throttle time,
anonymous RSS, page cache, memory pressure, swap and OOM separately. Do not run
environment probes or package installation during timed acceptance.

Benchmark sequence: replay alone -> URSim + leader alone -> combined -> repeated
finalization -> bounded injected CPU/disk pressure. Measure URSim, decoder/feeder,
serial/bridge, control, matching, encoding, writing and verification separately.
Collect per-process/container CPU core equivalents, memory, I/O, queue peaks,
deadline misses and source-to-command latency. Back off workload experiments on
resource exhaustion; do not relax safety or silently slow a real-time gate.

The unified amd64 image on an ARM Mac includes emulation overhead. Test that
delivery artifact first; a same-source native-arm64 collector build is an optional
diagnostic comparison if dependencies support it, not a replacement for amd64
deployment validation. Separate native-vs-emulated and Mac-vs-PC conclusions.
Keep installed source/image identity in every report; preserve existing `current`
until a new image passes its required software and integration checks.

## 7. Acceptance matrix and proposed numeric gates

All new gates below initially are NOT RUN. The user approved the six-stage
plan and high-standard diagnosis; numerical targets remain explicit engineering
targets to assess, never reasons to silently relax the existing control gates.

| Gate | Required evidence |
| --- | --- |
| M04-A01 transport | Seven expected identities, torque-off acquisition, correct signed counts, one serial owner; 60 s isolated and 60 s loaded timing windows satisfying section 5; stale/repeated/reset/error paths reject control. |
| M04-A03 mapping | HOME reference and six verified signs; follower HOME plus immutable episode-relative baseline; 0/4096 boundary/reset tests; first command no jump; independent calibration round trip. |
| M04-A02/A04 HOME/HOLD | Repeated supported HOME, current-position torque-on without pursuing a stale goal, release/partial-enable failures; actual drift/load/thermal results. Manual operation cannot pass this gate. |
| M06/M09 following | Per-axis and combined leader motion; intended and sent targets distinct; limits and ownership enforced; camera/encoder stalls cannot block stop. Use the already approved UR stop policy: <=0.01 deg/s for 200 ms within 2 s, then <=0.05 degree hold drift over a 30 s observation. Leader limits remain separate. |
| M08 replay | Every replay wrist anchor accounted for, unique identities within each replay epoch, <=16.7 ms view skew, no invented payloads. Report preserved-source holes separately from new replay delivery losses; do not apply historical full-camera acceptance ratios to a selected accepted-frame fixture. |
| M11 workload | Three 640x480 RGB-D streams at real-time 30 Hz pacing; H.264 CRF20/veryfast/GOP30/no B frames, uint16 PNG level1; candidate group-work p95 <30 ms, writer queue <=3/4, zero overflow. Final-file RGB decode and every depth hash pass. |
| M09/M13 faults | Space stop, held/active discard, Ctrl+C, bridge loss, serial stale stream, recorder failure, source restart, bad calibration and partial file. Faults cannot resume automatically or commit successful demonstrations. Inject logical faults first; do not unplug powered motor-chain wiring. |
| M10/M11 provenance/export | Raw leader/gripper input, calibration, mapped intent, sent command, simulated actual feedback and camera replay identity survive MCAP/JSON round trip; old recordings remain readable; one LeRobot export passes its existing validation. |
| M13-A03 batch | 20 accepted 40 s episodes after short/fault tests, exact boundaries and independent verification. All use physical leader input; looped cameras are labelled. No failed/interrupted episode counts toward twenty. |

For Hand-E, retain ID7 raw counts and derived Robotiq raw command separately.
Never fill absent actual Hand-E feedback with the requested command. A test server
may validate client behavior, but cannot close physical M05 acceptance.

Deliver a reproducible launcher, configuration/calibration snapshot, source/image
manifest, timings, fault traces and concise module acceptance report. Use temporary
artifacts for raw evidence; update formal docs after implementation. No claim of
physical UR teleoperation, USB-camera performance, complete HOME/HOLD or sustained
leader load acceptance beyond the tests actually performed.

## 8. Remaining decisions and current execution boundary

- Determine adapter identity from read-only USB inventory; confirm ID3 clearance
  before any active movement. Current posture is not automatically a reference.
- Ask the operator to confirm the exact calibrated HOME fixture and each physical
  direction before accepting mapping or executing follower motion.
- All motor register writes (including baud, indirect addressing, torque, profile
  and goal) await explicit operation-specific confirmation. No script in this
  increment may send these as a side effect of diagnostics or imports.
- Episode-relative mapping is aligned; implement section 2 without relaxing
  the independent HOME/HOLD accuracy investigation or hiding measured residuals.
- Record PASS/FAIL/NOT RUN per stage below; promote no historical measurements to
  new-source acceptance. No new physical UR12e access is authorized.

## Execution record

### 2026-09-11: read-only foundation and first measurements

Historical implementation record: absolute-only engagement below predates the
subsequent episode-relative decision in section 2.

Implemented explicit `devices leader` diagnostics with a serial wire allowlist,
exclusive ownership, monotonic acquisition intervals, signed readback, complete
seven-device replies, preserved motor status-error flags, and evidence output.
Standard and officially supported Fast Sync Read are selectable. No motor write
method exists in this adapter. The old unavailable production GELLO interface
remains unavailable; these diagnostics do not silently make it ready.

Implemented fixed calibration types and offline `calibrate leader-reference` /
`leader-validate` commands. No episode offset or automatic rebasing is accepted.
A stable trace is not a physical HOME or direction attestation. Reference
stability currently requires >=30 samples over >=1 second, <=2-count spread and
no >100 ms source gap. Actual HOME and all six directions remain uncalibrated.
The user confirmed no post-handover disassembly, direction or HOME changes.

Seven physical devices responded at 57600 baud: model 1060, firmware 50,
Operating Mode 3, Drive Mode 0, Torque 0, no hardware errors and watchdog 0.
Temperatures were 34-38 C; reported voltage 11.9-12.1 V. PID raw values were
P=640, I=0, D=3600. Profile velocity/acceleration were both zero at inspection.
Those are current reads, not proof of the settings used in historical loaded
HOME trials. Current goal/trajectory equal position with torque off, which
provides no loaded positioning-accuracy evidence.

Positions by ID were `[3160, 1616, 3123, 2057, 100, 1005, 3279]` counts.
ID5=100 is outside the old 1500..4000 interval; do not wrap it or overwrite HOME.
The user confirmed the ID3 cable issue remains unresolved. Keep active ID3
motion disabled until an explicitly verified cable-safe interval/path exists;
a future clamp must not silently replace the interlock. Other joints can also
pull the elbow cable. Record any clamp as a distinction between intent and sent
command; do not call saturation accurate tracking.

| Five-second read experiment | Fresh groups/s | Acquisition p99 / max |
| --- | --- | --- |
| Standard sync, seven positions (4 bytes each) | 31.15 | 33.64 / 46.20 ms |
| Standard sync, seven position+velocity blocks (8 bytes each) | 20.83 | 48.03 / 48.45 ms |
| Standard sync, seven full state blocks (83 bytes each) | 7.81 | 128.02 / 128.02 ms |
| Fast sync, seven positions | 31.06 | 35.43 / 72.21 ms |

All four runs completed without status errors, and before/after torque stayed
zero. None establishes the 50 Hz minimum or 100 Hz acquisition target. The
~16 ms timing steps motivate USB/VCP buffering diagnosis, but do not alone prove
its cause. The full layout fails the intended 100 ms freshness boundary.

A host-only macOS IOSSDATALAT experiment was accepted by the OS, then reads no
longer received replies. Restore attempts using documented default zero and
16 ms did not restore communication; even a one-second model read timed out.
The user confirms no power, cabling or competing-program change during the run.
USB serial enumeration remains present. This is an unresolved host/transport
failure, temporally associated with that experiment, not a diagnosed motor fault.
The host-latency option was removed from mainline. Its source and failed reports
remain in local evidence; no motor writes were sent. A Mac-side USB reconnect
has been requested while retaining 12 V, TTL wiring and physical support.
Do not continue active testing or automatically reset/reconfigure the motors.

Read-only evidence: `artifacts/gello/read-only-inventory-02`,
`timing-{position,motion,full}-01`, `fast-default` and host-latency reports.
The initial sandbox serial-open failure has zero transmitted instructions and
is preserved separately from hardware results.

The replay cache builder is isolated under `tests/replay/`. All three input MCAP
SHA256 values matched the supplied manifest. The two successful episodes decoded
to removable disk caches: 898/899 groups and 4,137,984,000/4,142,592,000 raw bytes.
Every source depth hash was checked and source group/clock metadata retained.
The partial episode remains failure evidence only. This accepts cache preparation,
not timed replay, mixed-source recording or a resource-loaded control session.

Software validation:

- PASS: 33 colleague snapshot tests in an isolated, network-disabled container.
- PASS: native suite, 310 passed / 5 skipped; skips cover unavailable native ROS
  and opt-in container checks. Run outside the sandbox for shared-memory tests;
  the initial sandbox failures are environmental, not hardware acceptance.
- PASS: rebuilt Ubuntu amd64 development image with ROS Jazzy loaded,
  313 passed / 2 opt-in container checks skipped in 22.20 s. No network or devices
  were exposed to the test container.
- PASS: both opt-in container replacement/mount checks, launched from the Mac
  against the rebuilt image, 2 passed in 3.59 s.
- PASS: 13 focused transport, mapping and replay-cache tests after the final
  schema validation change; Black and Pylint (10.00/10), with no lint findings.
- PASS: installed source SHA256 matches all 63 current package Python files.

The isolated working-tree image is `ur12e-collection:gello-development`,
`sha256:9abd925556416da45201dfd09b1ca948bd2f38890fe5bcd89838b2c458bed946`.
It is not a committed release or deployment; `ur12e-collection:current` remains
unchanged. New dependencies are `dynamixel-sdk==4.0.5` and `pyserial==3.5`;
other locked versions were retained. Native leader-only installation uses
`requirements/leader.txt`. Logs are under `artifacts/gello/`.

No motor motion, baud/indirect-address setup, PID tuning or new follower motion
has been performed in this increment. S3/S4/S6 remain NOT RUN. S5 has cache
preparation only; S1 high-rate acceptance and S2 physical calibration remain open.


### USB reconnect recovery and diagnosis

The operator reconnected only the Mac USB adapter and authorized further reads.
Communication recovered without motor register writes or another host-latency
change. All seven devices retained the inspected configuration (identity,
mode/direction, offset, hardware limits, torque, PID, watchdog, PWM and profiles).
Torque remained zero and hardware/status errors were zero. This establishes
recovery after USB re-enumeration, not the exact cause of the earlier failure.

| Read-only check | Result | Rate | Acquisition p99 | Maximum source gap |
| --- | --- | --- | --- | --- |
| Seven positions, 5 s | PASS, 157 groups | 31.25 Hz | 32.03 ms | 32.09 ms |
| Seven positions, 30 s | PASS, 936 groups | 31.19 Hz | 32.45 ms | 47.21 ms |
| ID1 position, 3 s | PASS, 188 reads | 62.54 Hz | 16.24 ms | 17.06 ms |
| ID1 position/velocity, 3 s | PASS, 188 reads | 62.51 Hz | 16.08 ms | 16.19 ms |

Evidence: `artifacts/gello/usb-replug-{position,stability}-01/report.json`
and `artifacts/gello/usb-replug-single-read.json`. Traffic contains only READ
and SYNC_READ. S1 communication recovery passes; the >=50 Hz all-device rate
gate still fails. A single motor is not a substitute for a fresh seven-motor
sample. The repeatable 16/32 ms steps strengthen the receive-buffering hypothesis,
but baud, adapter and OS contributions still need controlled comparisons.
Do not repeat the failed IOSSDATALAT experiment or add competing serial readers.
Retain one serial owner and separate camera/codec work. A baud migration or
motor-side return-delay/indirect setup requires a concrete procedure and explicit
confirmation before writes; no such migration has been performed.

Answering the current hardware questions:

- Power and torque enable are separate. The current powered, torque-off arm can
  report position while offering no active servo support. Its need for manual
  support does not establish inadequate powered holding torque.
- The old +/-20-count arrival gate allows about 1.76 degrees. Separate this
  software tolerance from encoder residual, physical calibration, backlash and
  load deflection. Current I=0 is a diagnostic variable, not a proven cause.
  Compare supported and loaded holds after motion approval before any tuning.
- The initial recommendation was strict fixed mapping; the subsequent user
  review supersedes it with section 2. Homing precision and the mapping definition
  remain separate concerns.
- Revalidate physical HOME and axis signs. ID5 still reads 100 counts outside
  its historical interval; do not treat the current desk pose as a new HOME or
  silently wrap it. ID3 remains blocked until cable-safe bounds are verified.
- The removable replay caches are prepared, but combined URSim/leader/replay
  resource acceptance remains NOT RUN. Mac results cannot substitute for the
  Ubuntu hardware gate or recreate absent historical resource time series.

### Episode-relative implementation and maintenance boundary

The user authorized development after the mapping revision, with a stop before
control/configuration signals. Implemented `leader/episode.py` as a pure intent
generator: stationary/fresh follower HOME, at least three stable leader samples,
one immutable baseline, direct delta mapping and a detached context record.
Source restart, stale/repeated/reordered samples, branch/range violations and
follower target bounds latch failure. Episode stop retires the baseline. Different
leader start angles produce equal follower deltas; no incremental integration
or cross-episode accumulation is used. Shared M06 rate/stop enforcement remains
required when connecting this generator to the owner; no device calls occur here.

Calibration schema 2 now represents fixed joint calibration, independently of
mapping mode. Its canonical ID includes the source evidence hash. The existing
`calibrate leader-reference|leader-validate` entrypoints remain offline and report
no physical readiness. The unreleased absolute-only schema 1 is rejected rather
than silently interpreted as the new behavior. Physical calibration and complete
activation remain pending. The context method prepares M10 provenance, but its
MCAP/session integration has NOT RUN; do not infer persisted baseline acceptance
from the detached-record unit test.

The [baud migration tool](baud-migration.md) is implemented and its read-only
physical preparation passed. Stop before `apply`: no register 8 writes, torque,
servo/HOME commands or physical UR access occurred. ID3 motion stays blocked.
No full leader-to-URSim or combined replay batch has been accepted by this change.

Software results on 2026-09-11:

- PASS: 35 leader transport/calibration/relative-mapping/maintenance tests.
- PASS: native full suite, 334 passed / 5 skipped in 9.11 s; skips are native ROS
  availability and opt-in container checks.
- PASS: amd64 Ubuntu/ROS Jazzy image suite, 337 passed / 2 opt-in checks skipped
  in 21.27 s, with network disabled and no hardware exposed.
- PASS: both opt-in container replacement/mount checks, separately run from Mac.
- PASS: Black, Pylint 10.00/10 with no findings and `git diff --check`.
- PASS: SHA256 comparison of all 65 installed package Python files against source.

Working-tree image `ur12e-collection:gello-development`:
`sha256:f827cb965224a821c20783372aa675f036e95d2c7ffa4a425cf77d6cd49ebf47`.
This replaces the previous development tag; the accepted `current` image remains
unchanged. It is not a committed release or a lab deployment. Evidence resides in
`artifacts/gello/development-*.log` and `relative-*.log`.

Next hardware action requires explicit confirmation: migrate only Baud Rate on
IDs 1..7 to 1 Mbps, verify each result and then run read-only timing comparisons.
The prepared plan and exact unexecuted command are in the migration plan.

### Approved baud migration and isolated read result

The user subsequently authorized only the baud migration and read-only timing.
The [migration record](baud-migration.md) contains all three attempts: two stopped
before writes on inactive goal/position changes, then the corrected and tested
preflight allowed the guarded migration. Exactly seven Baud Rate writes were
ACKed and verified, including a final reopen at 1 Mbps. Torque remained off;
no physical leader/follower motion command or other register write was sent.

The 60-second seven-axis position/velocity run yielded 3,751 groups at 62.50 Hz,
source-gap p99 16.07 ms and maximum 20.62 ms, with no communication/status errors.
This passes the isolated >=50 Hz read-rate and gap checks only. Full-state reads
are still too slow (37.04 Hz); use compact feedback plus independently aged health
reads in future integration. The 100 Hz target and combined source-to-control/
recording workload remain open. Current native busy polling costs about one CPU
core; reducing that cost is a separate measured improvement. No dock replacement
or further motor configuration change is justified by these results alone.

Host connection facts are saved in ignored `config/local/gello-connection.json`;
explicit probes now use `--baudrate 1000000`. These facts do not activate the
unavailable production GELLO adapter or establish calibrated motion readiness.

### User-requested 3 Mbps comparison

The user explicitly authorized a 3 Mbps trial in pursuit of 120 Hz. The guarded
transition 1000000 -> 3000000 was added and tested before execution. Seven writes
to Baud Rate=5 were ACKed and verified; all motors remain torque off. The active
connection record now specifies 3000000 baud, with the 1 Mbps record retained.

The matching 60-second compact read test again yielded 3,751 groups at 62.50 Hz,
source-gap p99 16.09 ms and maximum 21.57 ms, without communication/status errors.
Fast Sync Read did not improve the compact rate; full-state reads improved from
37.04 to 43.41 Hz. The 120 Hz trial did not pass. An instrumented short trace
places most delay before the first nonempty application read; it is diagnostic,
not another acceptance benchmark. See the migration plan for detailed evidence.
No further baud, latency, torque or motion change was performed. Combined replay/
URSim/leader acceptance and calibrated motion remain pending.

## References

- [ROBOTIS XL430 official manual](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/): encoder resolution, position PID, PWM limiting and indirect registers.
- [M04 existing plan](../m04-gello-adapter/plan.md).
- [M06 simulator control](../m06-control-motion/simulator-control.md).
- [M08 resource/gate evidence](../m08-frame-matching/resource-gates.md).
- [M09 session plan](../m09-session/plan.md).
- [M10 contracts](../m10-data-contract/plan.md).
- [M13 simulator matrix](../m13-acceptance/simulator-matrix.md).

### Latest development image after the 3 Mbps trial

See the migration plan's final delivery record: native 338 PASS, container
341 PASS, unchanged environment/opt-in skips, no lint findings, and all 65
installed package files matching source. The development image is now
`sha256:c96e9fd201cd44c7fe2ece213eeb17ca2c0f8fcb0719d5f114ed3366aded1cee`.
Physical baud migration and isolated compact readback are accepted slices;
120 Hz, combined-load/control latency, calibration and powered HOME remain open.

## 2026-09-11 continuation: 60 Hz and the no-control boundary

The user selected 60 Hz nominal leader acquisition and deferred higher-rate
investigation to the Ubuntu hardware session. The bus stays at its verified
3 Mbps; no further register changes are authorized by this continuation.
The existing 50 Hz command loop remains unchanged. This continues the aligned
S1/S2/S5 scope; no new hardware-motion acceptance is implied.

Implementation sequence:

1. Add a persistent, exclusively owned read worker at nominal 60 Hz, compact
   position/velocity samples and independently aged 1 Hz health reads. Control
   observes a latest-sample mailbox; recording drains a bounded queue. Preserve
   acquisition intervals, raw units, source epochs and sequence numbers. Never
   catch up by inventing samples. Serial/status/gap/queue failures latch and do
   not reconnect automatically. Closing only closes the port.
2. Exercise real source lifecycle and offline episode mapping with fake buses,
   including stale data, bounded-consumer overflow, health errors and close.
   Supply a bounded read-only diagnostic entrypoint with JSONL evidence. Do not
   activate the production control adapter or bypass calibration requirements.
3. Extend the disposable replay tooling to feed cached real images through the
   existing matcher and writer with explicit replay identity and timing. Keep
   original acquisition/receipt evidence alongside the run. Replay is simulated
   camera input; concurrent physical leader evidence remains a distinct sidecar
   until the mixed-source archival contract is implemented and tested.
4. Run short isolated and combined read-only workloads where available. An idle
   URSim may remain running, but no control socket, goal, torque or HOME operation
   is started. Report actual rates/CPU/queues and verify the resulting archive.

Acceptance slices: M04-A01 persistent read ownership, 60 Hz configuration,
>=50 fresh groups/s, p99 source gap <=40 ms and maximum <=100 ms; M04-A03
fault-latched source/episode handover software; M08/M11/M13 replay matching,
real re-encoding, lossless depth and bounded buffering. Full S4/S6 control and
mixed-source recording, powered HOME/HOLD and physical calibration remain open.
No high-rate or latency-driver experiment is part of this increment.

### Persistent read and replay implementation record

Implemented a single read-only worker with 60 Hz nominal motion polling and
independently timestamped 1 Hz torque/hardware-error reads. The acquisition clock
and epoch never change when consumers inspect the latest sample. Four recent
samples support an immutable episode baseline; a separate 120-sample recording
queue fails on overflow instead of dropping. Motion gaps over 100 ms, old health,
status errors, disconnects and closure invalidate consumers. There is no automatic
reconnect, torque/goal API or activation of the production GELLO stub.

`python -m ur12e_collection.leader.stream --port DEVICE --baudrate 3000000
--seconds 30 --output NEW_DIRECTORY` captures position/velocity JSONL compatible
with the M12 reference analyzer, separate health JSONL, transport counts, timing
and process CPU/RSS. Reference analysis rejects mixed epochs; a stable desk pose
still never attests physical HOME, directions or motion readiness.

The disposable `tests/replay/` feeder runs three independently paced producers,
one-frame prefetch and bounded eight-frame queues through the existing M08/M11
matcher/session/writer. It waits for writer initialization before defining the
capture boundary. Cache/source identities and original timestamps are retained;
new monotonic replay times and explicit sequence strides support loops. Physical
leader evidence remains separate, not mislabeled as simulated archive content.

Early runs before the preparation barrier overflowed the four-slot writer on
both Mac and amd64 Docker. After preparation, the native 10-second run completed
299/300 groups with peak writer queue 1 and maximum queue delay 17.95 ms. The
amd64 run still overflowed (12 completed groups, mean group work 44.35 ms).
An additional prefetch run without a CPU quota and with 2.5 GiB memory also
failed. These container results are FAIL, not a reason to increase queue limits
or a prediction that the native Ubuntu PC will fail.

The initial 30-second persistent leader slice completed 1,638 samples, 54.57 Hz,
source gap p99 28.75 ms / max 41.60 ms, delivery-age p99 28.12 ms, queue peak 1,
and 0.78 CPU cores. Torque stayed off. This passes the isolated short >=50 Hz
slice, not the plan's full 60-second loaded transport gate or a claim of measured
60 Hz. Nominal cadence includes deliberate pacing and periodic health work.

The first combined attempt failed leader communication after 389 samples / 7.14 s
with no status packet. The source latched and closed without reconnect or writes.
A physical connection change has not been established. Its camera run completed
1,190/1,198 groups (99.33%), so it also failed the 99.5% single-episode grouping
gate even though all final image decoding/depth hashes passed. Writer peak was
3/4; maximum queue delay 86.89 ms; MCAP size 452,240,549 bytes. These failed runs
remain in ignored artifacts. The subsequent one-frame-prefetch comparison and
final software/image validation are recorded below.

Current resource ownership is one native serial worker (budget one CPU core plus
scheduler headroom), three replay producers, one matcher/submission owner, one
ordered writer and its asynchronous finalizer. The existing URSim container
remained running, with an observed 1.45 GiB memory usage and approximately
0.60 CPU cores before the run;
no simulator control interface was opened. Container quotas and Mac native
results are separate experiments. Full CPU-pressure, anonymous-memory, swap and
per-operation p95 instrumentation are still pending, so no final allocation or
complete M11/M13 performance acceptance is claimed.

### Final comparison and acceptance boundary

The final native prefetch comparison also failed: replay overflowed its unchanged
four-slot writer after 11.65 s; the separate read worker latched stale input at
12.81 s after 692 samples. Before failure, sample rate was 54.61 Hz, gap p99
30.14 ms and maximum 39.71 ms. No automatic reconnect, motor write, simulator
command, physical UR command or calibration activation followed either failure.
Both failed trials remain failed; their surviving prefixes are not acceptance.

A post-run Mac VM snapshot showed approximately 6.13 GiB in the compressor and
63 MiB free. Those are post-run observations, not a synchronized memory-pressure
trace or proof that memory caused either fault. The historical PC bundle does
not contain enough telemetry to reconstruct that trace. Stop loaded comparisons
on this host for now; do not lower rates or enlarge queues to manufacture a pass.

| Slice | Result |
| --- | --- |
| M04-A01 persistent source software | PASS: exclusive owner, independent consumers, bounded queue, health/stale/epoch/status/close fault paths; serial write allowlist remains enforced |
| M04-A01 short isolated physical read | PASS, limited 30 s slice: 54.57 Hz; 60 Hz is configuration, not achieved measured rate |
| M04-A01 loaded physical read | FAIL in two attempts; full 60 s loaded window not completed |
| M04-A03 / M12 reference plumbing | PASS offline: recent source samples feed immutable episode references; JSONL feeds calibration analysis; mixed epochs reject; no physical HOME attestation |
| M08/M11 replay mechanics | PASS software fixtures and one 10 s native replay; original times/depth/loop identity survive, no control sockets, no historical robot feedback substitution |
| M08/M13 loaded grouping | FAIL: first 40 s file is valid but 99.33% <99.5%; later prefetch run overflowed |
| M11 amd64-on-Mac throughput | FAIL with both 4 CPUs/2 GiB and no CPU quota/2.5 GiB; native Ubuntu comparison remains NOT RUN |
| M04-A02/A04, M06, M09, complete S4/S6 | NOT RUN: powered leader HOME/HOLD, live following and integrated episodes remain unaccepted |

Software regression: native Python 3.12 suite **355 passed / 5 skipped** (9.56 s),
Black **123 files unchanged**, Pylint **10.00/10 with no findings**, and diff
whitespace check passed. Skips retain native ROS availability and opt-in container
boundaries. The image validation record follows; no accepted release is replaced.

### Next work, before requesting motion

- Diagnose loaded serial failures on a stable host with synchronized process,
  memory/IO and source-age telemetry; keep 60 Hz nominal. Ubuntu higher-rate
  exploration is a separate later decision. Physical cable-change context remains
  unresolved unless the operator supplies it.
- Complete native-to-container clock mapping/transport and per-source archival
  provenance before combining physical leader data with replay/URSim records.
  This increment deliberately does not label separate JSONL as integrated MCAP.
- Integrate the source into M09 through the shared controller. The existing
  controller requires an advancing target each tick; a 60 Hz source can still
  deliver no new sample at some 50 Hz polls. Define and test hold/skip semantics
  that preserve source timestamps and freshness before connecting it. Do not
  turn repeated cached reads into new leader measurements.
- Finish physical reference/direction/range checks (including the old ID5 range
  conflict), then prepare supported HOME/HOLD validation with ID3 motion blocked.
  Any torque, goal, mode or other register change still requires user permission.
- Only after these gates, request the concrete motor/simulator motion test.
  No control authorization is requested while source/control prerequisites fail.


### Development image and final verification

Rebuilt only `ur12e-collection:gello-development`, linux/amd64, source label
`f195db3-gello-60hz-working`:
`sha256:e26b3ccc60f1edbb0a5931e15a3297214d52f2bdd0fde00ea9d21b03d7eabfe8`.
All 69 installed Python/schema files match the working tree. Installed-image
Ubuntu 24.04 / ROS Jazzy tests: **358 passed / 2 opt-in tests skipped** in 23.94 s.
One harmless warning concerns pytest's unwritable `/opt` cache; no test failed.
Native tests: **355 passed / 5 skipped**. Checks and image identity are retained
in `artifacts/gello/60hz-*`. This is an uncommitted development image, not a
release, hardware acceptance or lab deployment. The accepted `current` tag is
unchanged.

Timed Docker replay used the preceding `c96e9fd201cd...` development image with
this iteration's disposable replay scripts mounted read-only. Its matcher,
writer and codecs are unchanged in the newly rebuilt image. The rebuilt image
passed software checks; a new timed hardware/integrated acceptance was not run.

## Operator calibration priority update (2026-09-11)

The user explicitly deferred multi-camera alignment and resource-pressure
investigation, retaining the failed evidence for later work. Those workloads are
not prerequisites for isolated, operator-assisted leader calibration. They still
block any claim of accepted integrated recording. Nominal acquisition remains
60 Hz at the existing 3 Mbps bus setting. Continue the aligned S2/M12 calibration
scope, then separately authorize bounded active motor tests.

Read-only preflight `artifacts/gello/calibration-preflight-20260911T054926Z`:
all seven XL430s responded in position mode 3, Torque Enable=0, hardware/status
errors=0. Counts in ID order were `[3158,1615,3185,2056,99,1005,3278]`.
This is not HOME. ID5 is outside its historical interval; ID2 is near its old
lower bound. Do not command any old HOME or mask either issue by wrapping or
clamping a calibration reference. ID3 cable clearance remains unresolved.

Operator sequence, within the already aligned calibration scope:

1. Support the arm and secure the base. Start with ID7 only: place its input at
   the natural OPEN position without forcing a hard stop, hold still, and signal
   readiness. Acquire a separate two-second read-only trace. Then repeat at
   CLOSED and return to OPEN. Capture the endpoints over three approaches;
   report actual residuals and reject unstable endpoint windows (>2 counts).
   OPEN maps to Robotiq raw 0 and CLOSED to raw 255. Preserve leader raw counts.
2. Identify each of IDs 1..6 by one manually moved joint at a time, starting
   with wrist3/ID6. Use small reversible excursions only within free cable and
   mechanical clearance; record every joint so unintended coupling is visible.
   A manually selected direction is only a labelled observation until matched
   against an explicitly identified UR-positive joint rotation. Clockwise without
   an observation direction is not a valid sign definition. Small approximate
   excursions establish identity/direction only, not angular scale accuracy.
3. Establish the supported physical HOME reference matching follower
   `[0,-90,-90,-90,90,0]` degrees, then measure stable counts, verified signs,
   usable branch/range, gripper endpoints and mechanical scale evidence. If
   cable clearance or support prevents it, keep the affected fields unvalidated
   rather than publishing a complete calibration. ID3 powered movement stays
   disabled; even manual checks must not tension its cable. ID5's old interval
   must be reconciled before active commands on that axis.
4. After passive input alignment, prepare a one-axis active command test:
   seed the current measured position, use explicitly bounded nonzero profiles,
   verify torque-enable/holding behavior, then a small reversible displacement.
   Name the motor, goals, limits, support and stop behavior before requesting
   the user's specific start confirmation. No torque, goal or mode write is
   authorized merely by readiness to help. Retain the stricter HOME accuracy
   investigation; do not accept the old +/-20-count threshold.

Keep input calibration, successful command reception, encoder arrival and
external mechanical accuracy as separate results. Do not treat a status ACK as
successful motion or manual holding as powered HOLD acceptance. No physical UR
control is in scope; URSim following is a subsequent separately started test.
No new motor writes or calibration activation occurred during this update.

### One-session operator capture (2026-09-11)

The user superseded per-pose chat coordination with one scripted sequence and
post-run log analysis. This is a workflow change within aligned S2/M12; implement
one passive guided capture, without waiting for each pose confirmation in chat.
Use the existing 60 Hz read-only source, bounded recording and failure latch.
No camera replay, resource benchmark, follower connection or motor write runs.

The sequence lasts 250 seconds: 20 s preparation, 5 s reference hold, six 30 s
joint slots in ID order, three OPEN/CLOSED cycles (5 s per endpoint), 10 s return
to the reference and a final 5 s hold. Each joint slot comprises rest 3 s, move A
4 s, hold A 3 s, return 4 s, move B 4 s, hold B 3 s, return 5 s, rest 4 s. A means
counterclockwise viewed from the motor output-shaft end toward the motor; B is
the reverse. Use small comfortable excursions around 5-10 degrees, not claimed
measured scale references. Maintain one viewing convention and only move the
named joint. Do not rotate to a hard stop. ID3 stays still unless manual motion
has free cable clearance; no powered elbow motion is permitted. Gripper endpoint
windows use their last two seconds, excluding the repositioning interval.

Capture planned phases plus actual cue timestamps, raw seven-axis samples,
health and terminal/optional spoken prompts. The operator launches once when
ready and sends one completion message. The assistant does not poll samples or
analyze movement during the run. Local health/freshness/torque monitoring remains
active so the recorder fails visibly on bad input; it never tries to correct
motion. Ctrl+C closes the read port and preserves the incomplete evidence.

Offline output includes stable endpoint estimates, reference spreads, per-axis
A/B deltas, non-target-axis changes, returns, branch discontinuities, timing and
all failure/pending reasons. Test the whole workflow with injected samples and
faults, including delayed cues and incorrect torque. Do not automatically publish
an active calibration or infer UR signs, exact gearing, mechanical limits,
physical HOME accuracy or powered arrival from passive encoder traces. An
operator HOME declaration is retained separately from independent validation.
Complete the batch's observable inputs together, then ask only for unresolved
physical facts in one follow-up. Preserve all existing failed workload results.

The guided capture and offline analyzer are implemented as
`calibration.leader_batch` and `calibration.leader_review`, reusing the existing
read-only source and shared trace serializers. The complete virtual sequence and
fault cases passed; final native regression: **362 passed / 5 skipped** in 10.07 s,
Black **126 files unchanged**, Pylint **10.00/10, no findings** and whitespace
checks passed. No hardware capture or motor write was started during development.
The [single-session runbook](../m12-calibration/leader-batch.md) supplies the exact
operator command and sequence. Physical outcome remains pending the operator's
one-shot run; this increment did not rebuild the Docker development image.

### Compressed operator sequence (2026-09-11)

The operator is already positioned and explicitly removed the 20-second
preparation, requesting 10 seconds per motor. Replace the 250-second default
with an 80-second sequence: initial reference hold 5 s, six joint slots of
10 s, one lever/gripper slot of 10 s, final reference hold 5 s. Joint slots use
move A / hold A / move B across reference / hold B / return, 2 s each. Analyze
only the actual 2-second holds, and use initial/final whole-arm references for
return errors; never include preceding motion by extending a short hold window.

ID7 is a motor with a lever, not a jaw. Define this capture's operator convention
explicitly: counterclockwise-side position represents OPEN (Robotiq raw 0),
clockwise-side position represents CLOSED (255), using the same output-shaft
view. This software convention is reversible; do not infer an intrinsic jaw
state or import the old endpoints. Its slot has two 2-second movements, two
2-second endpoint holds and a 2-second return. A single pass does not establish
three-approach repeatability; report that field as unverified. This revision is
passive only and does not authorize motor writes or activate a calibration.

The 80-second protocol and lever convention are implemented. Its offline reviewer
uses initial/final whole-arm references rather than pretending 10-second slots
contain separate return holds. Single-pass lever endpoints explicitly retain
unverified repeatability. Validation: 27 focused tests passed, Black and Pylint
passed with no findings, and whitespace checks passed. No physical batch or
motor write was started while making this revision. The exact operator sequence
is in the updated M12 runbook; the existing startup command selects the new default.


Minimal timing revision (2026-09-11): the user changed each motor slot to 20 s.
Each of its five steps now lasts 4 s, including the ID7 lever slot. Initial and
final reference holds remain 5 s each, giving 150 s total (`passive_150s_v3`).
Directions, passive-only behavior, offline hold-window analysis and all gates
remain unchanged. This supersedes the 80-second schedule without motor writes.
Validation: all 7 guided-batch tests passed; Black and whitespace checks passed.

### Completed operator batch review

The 150-second operator run `operator-batch-20260911T142353` completed with 8,161
samples at 54.404 Hz, no communication/status errors and all observed torque off.
The user reports reversed wrist2 A/B input; preserve this as an analysis-only
semantic correction. Full findings are in the
[M12 operator review](../m12-calibration/operator-review-20260911.md).
Several fixed hold windows contain motion, particularly wrist3 and lever OPEN;
input response does not imply completed stationary calibration. ID5's continuous
negative feedback is valid torque-off behavior according to the manufacturer,
exposing the current single-turn calibration-input restriction as required
software follow-up. No motion, configuration write or calibration activation was
performed during this offline review. Loaded camera/resource gates remain deferred.

HOME semantics were clarified by the operator: use an actual initial-reference
sample, never an intermediate movement median or an initial/final average.
Selected HOME sequence 273 and the separate final-return sample are retained in
the M12 review. Lever input is independent: assigned OPEN=3256 and CLOSED=3388,
without claiming mechanical endpoint accuracy. The actual-sample reference
implementation passed 39 focused tests; active handover remains unimplemented.

### Reviewed baseline commit

2026-09-11: the user authorized committing the completed passive leader work
and proceeding with the [offline completion nodes](../m13-acceptance/offline-completion.md).
Native regression: 363 PASS / 5 environment skips; Black and production/script
Pylint PASS. Replay workload failures and active-control limitations above remain
open. Manual source/context review and credential-pattern inspection found no
credentials in the selected change; no automated secret-scanner claim is made.

### N1 signed reference and assigned lever mapping

Aligned by the offline completion plan on 2026-09-11. Calibration schema 3
explicitly supports signed 32-bit teaching coordinates; old schema 2 requires
review and regeneration rather than silently changing its gripper semantics.
Configured joint bounds remain mandatory and no modulo wrapping is performed.
Assigned gripper endpoints saturate to Robotiq raw 0..255 independently of
mechanical travel. The actual initial sample remains the reference.
`PoweredAxis` binds an explicitly measured logical/powered offset to one epoch
and rejects stale epochs or goals outside the configured mode-3 interval.
Binding creation does not attest a stationary physical transition.

M04-A03 / M12-A05 software slice PASS: 28 focused mapping, episode and guided
capture tests, including negative input and a torque reset. Physical calibration
and powered transitions remain NOT RUN. No motor writes occurred.

### N2 shared leader source and conditioned commands (2026-09-11)

The aligned offline completion scope now connects an injected leader source to
the existing session. Raw signed acquisitions, fixed calibration and the immutable
episode baseline remain distinct from evaluated intent and sent command events.
The acquired authority event embeds the baseline and calibration; this is the
per-episode context because codec preparation precedes the final start reference.
The snapshot declares `episode_relative_conditioned_v1`. No baseline is silently
changed during preparation or recording.

Quantized encoder differences can exceed a finite-difference acceleration gate
even for slow movement. A bounded command conditioner therefore limits velocity
and acceleration (90% numerical headroom), while joint intent outside limits
still faults. This is explicit command shaping, not altered sensor data. Command
sequence/time describe generation; each intent also contains the original raw
source epoch, sequence and acquisition times. Reusing fresh input does not renew
its 100 ms age bound. Independent archive checks reconstruct relative intent and
check sent-command position, step, velocity and acceleration. Failed source or
closed ownership cannot resume with the same baseline.

URSim smoke PASS: one 8-second episode using the completed operator trace at
3.5x replay speed and synthetic cameras; 240 image groups, stop/HOLD and independent
file verification passed. Native focused tests cover reuse/staleness, epoch reset,
1,200 jittered/reversing conditioner steps and forged archive values. Simulation
signs/ranges and accelerated replay do not accept physical calibration.

### N3 coordinated motion software

An injected `Motion` transport now provides staged current-position hold, powered
HOME and explicit supported torque-off leading. Single-turn bindings must be
provided and checked before torque enable; goals are preloaded before enable.
No physical serial write transport or production factory is enabled.
ID3 is blocked by default; coordinated HOME refuses before any motor write when
any axis lacks clearance. The simulated fixture explicitly clears its own cable
constraint and models coordinate resets, lag, residual error and torque loss.

The shared session requires both follower HOME and leader HOME before READY, and
waits for leader HOLD after stopping the follower. Reference acquisition occurs
after supported release. The software target is <=2 counts for 200 ms, not the
historical 20 counts. This does not establish physical load capability or absolute
accuracy. Fault hold is best effort and logged; no automatic torque-off on close.
The [ROBOTIS control table](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/)
defines signed feedback and torque-reset behavior; real transition binding and
profile parameters remain hardware gates. Six motion/coordinator tests and four
local Hand-E wire tests PASS. Full integrated simulation is being rerun.
