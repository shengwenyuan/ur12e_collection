# M06: Operator-Approved READY Interruption Test

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned for test-code development on 2026-09-11; physical launch pending
explicit operator permission. The user chooses the current safe pose as the
starting point and READY return as the test movement. The assistant may prepare
and validate code now, but must wait for the operator to select Remote Control
and explicitly authorize the specific physical run before opening control.

## Scope and parameters

Keep this diagnostic under `tests/hardware/`, outside production entrypoints.
The production physical backend remains disabled. Use the pinned ur_rtde 1.6.5
SDK's asynchronous joint move and explicit joint stop; no stored PolyScope
program or installation is loaded. This verifies a READY-directed movement and
its orderly SIGINT stop, not the native Home node or full collection lifecycle.

- Target, in base/shoulder/elbow/wrist1/wrist2/wrist3 order:
  `[0, -90, -90, -90, 90, 0]` degrees, preserving angle branches.
- Move speed: 1 degree/s; acceleration: 2 degrees/s².
- Stop deceleration: 2 degrees/s², explicitly avoiding general SDK stop defaults.
- Inject actual SIGINT into the motion process two seconds after its logged
  move-request event, not two seconds after Docker startup.
- Independently record output-only feedback through at least 30 seconds after
  SIGINT. Preserve raw source times, receipt times, actual joints/velocities and
  runtime/safety states, plus command/signal events in flushed JSONL logs.
- Stop without returning or resuming. Do not command Hand-E, change TCP/payload,
  power/brakes, safety configuration or operational mode.

Preparation reads controller identity and current pose without importing the
control SDK. It writes a reviewable expiring plan containing the initial pose,
target, rates and expected joint changes. Execution requires an explicit operator
approval CLI flag, matching serial/host, Remote mode, normal safety, a stopped
program, fresh stationary feedback and a start pose within 0.1 degree of the
reviewed pose. Reject malformed or expired plans, out-of-range joints, angle
changes above 180 degrees and a start already too close to READY for a meaningful
two-second interruption. These numerical checks do not establish collision-free
motion: the operator must approve clearance along the intended initial segment.

## Implementation and validation

1. Add a standalone prepare/execute harness and offline audit under tests/hardware.
   Reuse the project read-only identity/coherent-state helpers. Keep the observer
   and motion owner in separate processes, with an exclusive host-specific test
   lease, bounded startup and fail-visible cleanup. Only the motion owner creates
   the control SDK and maintains its 5 Hz controller watchdog.
2. Keep the SDK alive through explicit stop and observed standstill before ending
   its script. SIGINT requests stop; it must not kill the feedback observer.
   A host watchdog is defense in depth, not this test's accepted fault mechanism.
3. Test plan rejection, exact move/stop parameters, interrupt handling, premature
   completion and truthful audit failures with fake dependencies.
4. Run the actual harness against isolated official URSim, including a displaced
   starting pose and at least 30 seconds of observed hold. No lab control during
   development or simulator validation.
5. Stage the validated files on the lab PC and report their checksums. Obtain a
   fresh read-only initial-pose plan and present its movement for operator launch
   permission. Do not run execute merely because Remote mode becomes available.

## Acceptance

M06-A02/A03 and M03-A02 diagnostic slices: verify actual motion before SIGINT,
correct target/rates, prompt signal dispatch, no source rollback or material
feedback gap, observed rest within one second of the stop request, and at least
30 seconds of post-signal observation. Require observed speed <=1.2 degrees/s,
rest speed <=0.01 degrees/s and post-settle joint drift <=0.05 degree. These are
test thresholds, not certified safety limits. If READY is reached before SIGINT,
report the interruption case as inconclusive. An interrupted return is not full
READY arrival acceptance. Missing data cannot establish successful stopping.

SIGKILL, network loss, camera/recorder faults, physical limit-trigger behavior,
GELLO and full end-to-end control acceptance remain separate.

Reference: [ur_rtde asynchronous move and stop example](https://sdurobotics.gitlab.io/ur_rtde/pages/examples/basic_motion/move_async_example.html).

## Results

Implemented as an isolated diagnostic, with no production control changes:

- `tests/hardware/ready_interrupt.py`: read-only `prepare` and explicitly approved
  `execute`; independent observer and signaled SDK owner.
- `tests/hardware/ready_audit.py`: offline motion/direction, dispatch, stop, hold,
  feedback continuity and command-parameter gates.
- `tests/hardware/run-ready-test`: pinned-image non-root Docker launcher; audit
  runs with networking disabled. No camera/USB access is needed for this test.

| Check | Actual result |
| --- | --- |
| Mac diagnostic tests | PASS: 19 cases |
| Mac diagnostic plus shared control regression | PASS: 48 cases |
| Ubuntu pinned image, networking disabled | PASS: same 19 diagnostic cases |
| Black / Pylint / shell syntax / diff whitespace | PASS; Pylint 10.00/10 |
| Actual isolated URSim, asymmetric displaced initial pose | PASS: all 13 audit gates; 3,132 observed samples |
| SIGINT timing / stop dispatch | 2.007102 s after move request; stop request 0.000647 s after signal |
| Measured stop / subsequent hold | 0.402922 s to observed rest; 30.008958 s post-signal observation; zero observed hold speed/drift |
| Motion / feedback | Peak 1 degree/s; max source gap 16 ms, receipt gap 37.644 ms, cached-state age 65.536 ms |
| Physical launch | NOT RUN; explicit operator permission still required |

The first URSim run correctly failed its audit after the harness interpreted
`stopScript()`'s Python return value as a boolean. The pinned binding declares
`stopScript(...) -> None`; its observed stop/hold was preserved but not accepted
by that run. The corrected harness calls the void method and independently
requires the observer's stopped-runtime and hold gates. A regression covers the
void return. No physical control was used to diagnose or correct this issue.

Passing simulator evidence:
`artifacts/ready-interrupt-validation/1789087821059720000/`, containing frozen
sources, image/peer identity, per-file hashes, initial-pose plan, raw trace and
audit. The failed predecessor `1789087735531234000` is retained. The client image
is `sha256:a3d22d1ffa6c36331116a4c870f7bb841d84ec036cd9a2d23460345ce15bab96`;
the isolated official simulator remains URSim 5.22.2. Simulation metrics are not
physical acceptance evidence.

## Lab staging and pending launch

Test release `3363de20dba9` is staged at
`/home/robot2026fall/ready-interrupt-test-3363de20dba9/`. Local
`artifacts/ready-interrupt-validation/release.json` records exact hashes; remote
SHA-256 readback matches all four files. The production image and station file
were not replaced. The original physical backend still rejects connection.

A read-only preparation through the verified direct Ethernet route succeeded.
Controller `20255100083` is normal, stationary, and still Local. Observed initial
angles were approximately `[12.887, -95.743, -90.000, -96.577, 82.505, -7.474]`
degrees. The target remains `[0, -90, -90, -90, 90, 0]`; largest target difference
is base -12.887 degrees. This is numeric review, not clearance verification.
No SDK control object was created. The stored review expires after ten minutes
and execution rejects any initial-pose change above 0.1 degree.

For a fresh review (read-only), on the collection PC:

```sh
bash /home/robot2026fall/ready-interrupt-test-3363de20dba9/hardware/run-ready-test \
  prepare --host 10.18.1.106 --serial 20255100083 \
  --output /evidence/<new-review>.json
```

Only after explicit operator permission for the reviewed short return segment,
with the operator at the emergency stop and Remote Control selected:

```sh
bash /home/robot2026fall/ready-interrupt-test-3363de20dba9/hardware/run-ready-test \
  execute --plan /evidence/<approved-review>.json \
  --output /evidence/<new-run> --operator-approved
```

Then independently audit the run, without any robot connection:

```sh
bash /home/robot2026fall/ready-interrupt-test-3363de20dba9/hardware/run-ready-test \
  audit /evidence/<new-run>
```

Evidence is persisted under `/home/robot2026fall/ready-interrupt-tests/`. No command
above changes the operator's configured installation or starts a return after
interruption. The tested signal path is specific to the SDK motion owner; it
does not qualify the mainline Space/Ctrl+C session or the native Home program.

## First authorized physical run (2026-09-11)

The operator explicitly instructed the assistant to start after the agreed
emergency-stop/Remote-Control preparation. The assistant verified the staged
file hashes and direct Ethernet route, then performed a fresh read-only review.
Remote Control was true; serial matched, safety was normal, the program was
stopped and the pose differed by less than 0.003 degree from the previously
presented start. Only this one physical run was launched; no retry or return
followed it.

Execution used release `3363de20dba9` and
`review-20260911-3363de20dba9-launch01.json`. Evidence remains remotely at
`/home/robot2026fall/ready-interrupt-tests/run-20260911-3363de20dba9-01/`
and locally at `artifacts/ready-interrupt-physical-20260911/`. The audit ran
afterward in a separate network-disabled container. All test containers exited.

Overall strict acceptance: **FAIL**, with 11 of 13 gates passing. Actual motion
followed the requested READY direction, SIGINT invoked the explicit stop path,
and the robot stopped without continuing to READY. Two predefined numerical
gates did not pass; do not relax them or substitute the simulator result.

| Measurement / gate | Physical result |
| --- | --- |
| Motion and reviewed command | PASS; peak observed joint speed 1.05338 degrees/s, below 1.2 |
| Timed SIGINT | PASS; 2.007074 s after movement request |
| Stop dispatch | PASS; stop request 0.000186 s after SIGINT dispatch |
| Time to first sample <=0.01 degrees/s | FAIL against <=1 s gate: 1.065264 s |
| Hold from that first low-speed sample | FAIL against <=0.01 degrees/s gate: subsequent peak 0.026269 degrees/s; drift from first sample 0.006038 degree |
| Independent observation | PASS; 3,169 samples, 30.005633 s after SIGINT |
| Feedback | PASS; maximum source gap 16 ms, receipt gap 10.719 ms; no rollback or cached-state plateau |
| Robot/program state | PASS; normal robot/safety states, final program stopped |
| Completed READY return | NOT RUN; deliberate interruption occurred before arrival |

Initial observed joints were approximately
`[12.8872, -95.7427, -89.9993, -96.5769, 82.5051, -7.4721]` degrees.
Final observed joints were
`[10.7782, -94.8067, -89.9953, -95.5021, 83.7320, -6.2503]` degrees.
The robot held this intermediate pose; no new target, gripper action or
configuration change was sent after the stop.

Offline tail inspection localizes the strict hold failure to settling near the
first low-speed crossing: speeds in the first 0.5 seconds after stop ranged
approximately 0.505..0.994 degrees/s; during 0.5..1.0 seconds, 0.040..0.525;
during 1.0..1.2 seconds, 0.0097..0.0263. After the SDK owner finished, the remaining
28.53-second observation had peak speed 0.00517 degrees/s and maximum per-joint
span 0.00793 degree. The last 20 seconds had peak speed 0.00144 degrees/s.
These support subsequent stable hold, but do not turn the original first-crossing
gate into PASS or establish a 30-second post-settle hold interval.

Next alignment: distinguish deceleration/settling time from the stable hold window
and investigate the physical stop response before any gate or parameter change.
No cause is inferred from speed readback alone. No automatic rerun is authorized.
SIGKILL, network loss, recorder faults and full production-session stopping
remain untested on physical hardware.

## Authorized ten-second repeat (2026-09-11)

The user explicitly authorizes one additional physical run with interruption
after ten seconds. Keep READY, the 1 degree/s speed, 2 degrees/s² acceleration
and deceleration, post-signal 30-second observation and existing audit thresholds
unchanged. Add an explicit 2-or-10-second preparation parameter; save it in the
review and use that same value for signal timing and audit. Do not edit or
overwrite the earlier release or its evidence.

Before this repeat, check that the current pose matches the previous stopped
pose and provides sufficient travel for motion still to exist at ten seconds.
Require at least `interrupt_after_s * speed_deg_s + 0.5` degrees of leading-axis
distance (and the original four-degree minimum). Read-only preparation and
offline tests precede the single authorized launch. If preflight fails, stop
without moving or automatically choosing a different pose. The earlier strict
stop/hold failures remain recorded; increasing the timer does not relax them.

### Ten-second repeat results

The timer change passed 22 offline cases on both Mac and the pinned Ubuntu
image (network disabled for those tests), Black, Pylint 10.00/10 and shell syntax
checks. New tests exercise actual observer scheduling with a controlled clock
at both 2 and 10 seconds, preservation of the 30-second observation, and rejection
of insufficient remaining travel. Release `cc022cbddeea` was staged separately;
remote hashes matched `artifacts/ready-interrupt-validation/release-10s.json`.
The earlier release and evidence were retained unchanged. No speed, acceleration,
deceleration or stopping/hold threshold changed.

Fresh physical preflight confirmed Remote mode, normal safety, stationary state
and the previously observed stopped pose within 0.003 degree. Maximum remaining
READY difference was 10.779 degrees, satisfying the 10.5-degree minimum for the
ten-second test. The assistant then executed the one explicitly authorized repeat.

Strict result: **FAIL**, with 12 of 13 gates passing. The only failed gate was
the unchanged one-second limit for the first observed speed <=0.01 degrees/s.

| Measurement | Result |
| --- | --- |
| SIGINT after motion request | 10.006154 s: PASS |
| Stop request after SIGINT | 0.000196 s: PASS |
| Time to observed rest | 1.157591 s: FAIL against <=1 s |
| Peak joint speed | 1.081453 degrees/s: PASS |
| Hold after first rest sample | Peak 0.009802 degrees/s; drift 0.004453 degree: PASS |
| Post-signal observation | 30.006531 s; 3,952 samples: PASS |
| Feedback continuity | Max source gap 16 ms, receipt gap 11.727 ms, no rollback or cached plateau: PASS |
| State and target behavior | Normal safety, stopped program, correct READY direction, interrupted before arrival: PASS |

Final joints were approximately
`[0.6744, -90.3037, -89.9970, -90.3446, 89.6072, -0.3925]` degrees.
Maximum residual READY error was 0.6744 degree. This was another interrupted
return, not full READY arrival acceptance. The motion owner ended normally,
the independent observer completed, and no test containers remained. No further
motion, automatic retry or continuation was issued.

Remote evidence:
`/home/robot2026fall/ready-interrupt-tests/run-20260911-cc022cbddeea-10s/`.
Local evidence: `artifacts/ready-interrupt-physical-20260911/10s/`, including
raw trace, plan, audit, final pose and launcher log. The audit was run offline
with networking disabled. The earlier stop-time and settling-tail observations
remain unchanged; this run does not redefine the acceptance limits.

## Approved settling-aware acceptance (2026-09-11)

Status: aligned for implementation. The user approved this exact revision and
requested a tested mainline image, commit and collection-PC deployment. Offline inspection of both
existing physical traces shows that stable confirmation can preserve the original
0.01 degree/s velocity threshold. No additional hardware run was started.

Approved policy: allow up to two seconds from the stop request to confirmation of a
continuous 200 ms interval with every joint at or below 0.01 degree/s. Reject
feedback gaps/rollback during that interval; repeated cached samples do not
establish duration. Measure hold only after this confirmation, keeping the
0.01 degree/s hold speed and 0.05-degree drift bounds. Retain the existing
30-second post-SIGINT observation and all motion, source freshness, watchdog
and prompt-stop-dispatch requirements. The two-second budget is an acceptance
window, never a delay before issuing the stop command.

Offline candidate measurements, without replacing either historical audit:

| Existing trace | 200 ms standstill confirmation after stop | Subsequent peak speed | Drift from confirmed pose |
| --- | --- | --- | --- |
| Two-second interrupt | 1.423885 s | 0.005165 degrees/s | 0.005150 degree |
| Ten-second interrupt | 1.362500 s | 0.004033 degrees/s | 0.005539 degree |

Both traces satisfy these proposed stop/hold criteria. This is a retrospective
candidate comparison, not a new physical run or a replacement PASS for the old
criteria. If aligned, implement the independent settling window and test transient
low-speed crossings, later motion, source gaps and deadline failures; write new
versioned reassessments while preserving original FAIL reports.


### Mainline integration and delivery scope

Use one fresh-feedback standstill window for SDK cancellation, native-program
cancellation, the isolated diagnostic cleanup and offline audit. Stop confirmation
uses 0.01 degree/s for 200 ms, with a two-second deadline; existing ordinary
waypoint arrival tolerances remain unchanged. No motion rate, stop deceleration,
watchdog or physical-backend enablement changes are authorized by this revision.
The audit is an installed offline module, with a versioned output that cannot
overwrite historical results. Hardware launch code remains under tests/hardware.

Implement and test transient crossings, cached timestamps, source gaps/rollback,
late confirmation and resumed motion/drift; reassess both preserved traces. Run
native and installed Jazzy regressions, package a source-matching amd64 image,
and verify deployment with networking disabled and existing mounts preserved.
The robot is now powered off: no new robot/camera checks or motion will run.
PC deployment is contingent on SSH availability; software validation remains
independent of lab hardware. Acceptance updates follow under M06-A02/A03 and
M01-A01/A02/A03; historical physical failures retain their original policy.


### Implementation and offline acceptance

M06-A03 **PASS for the approved controlled-stop diagnostic scope** by
retrospective `settling-v2` assessment of the existing two physical traces. Each
passes all 13 independent gates. Confirmation occurs at 1.423885 s and 1.362500 s;
post-confirmation speed/drift remain within the unchanged bounds above. New files
are `audit-settling-v2.json` beside each original `audit.json`; originals still
record FAIL under the one-second/first-crossing policy. No new physical test ran.
This does not establish full READY arrival, GELLO following, native physical
Dashboard cancellation, emergency stop, SIGKILL or network-loss acceptance.

The installed `control.settling` policy is shared by SDK/native cancellation,
the isolated diagnostic and `control.stop_audit`. Ordinary waypoint arrival
and engagement limits, stop dispatch/deceleration, feedback freshness and
watchdogs retain their previous values. The physical mainline factory stays
disabled. The diagnostic launcher selects `UR12E_IMAGE` or the current image;
previous frozen test releases remain unchanged.

Software validation: **297 PASS / 5 environment skips** on native Mac Python
3.12; Black passes and mainline/script Pylint is 10.00/10. The hardware harness
and its tests also score 10.00/10. The first sandboxed run had five local shared
memory/process permission failures; the same suite passed outside that sandbox.
Regression cases cover cache-only duration, transient low-speed crossings,
source gaps/rollback, inclusive speed/deadline boundaries, renewed motion, drift,
SDK/native stop timeouts and immutable historical reports. No test connects to
physical devices. Image and PC deployment results follow in the M01 delivery
record; these software results alone do not establish new physical acceptance.

Offline reassessment entry point (no SDK import or network):

```sh
python -m ur12e_collection.control.stop_audit /path/to/evidence
# Optional new destination; existing files are rejected rather than replaced.
python -m ur12e_collection.control.stop_audit /path/to/evidence --output /path/to/new-report.json
```
