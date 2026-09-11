# Offline Mainline Completion with URSim and Recorded Inputs

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Status: aligned / implementing; authorized by the user on 2026-09-11.
- Date: 2026-09-11.
- Primary module: M13; affected modules: M01-M12 and the reserved M14/M15 interfaces.
- Parent: [meta plan](../../meta_plan.md).
- Existing leader work: [M04 integration](../m04-gello-adapter/hardware-integration.md).
- Request: propose the remaining development and acceptance sequence using URSim,
  recorded three-camera inputs and a stub leader, without physical devices.

## Outcome and boundaries

Complete the agreed first-release software lifecycle and its simulation gates.
Do not label this full physical-system acceptance. Reuse accepted behavior and
rerun affected tests; do not restart all modules or duplicate the collector for
simulation. Keep actual UR, Hand-E and DYNAMIXEL writes disabled in this sprint.
URSim motion and isolated fake-device writes are the only control test targets.

Use the official pinned URSim setup already recorded in M06. Camera fixtures come
from `/Users/shengwenyuan/Downloads/ur12e-lab-replay-20260911`; leader fixtures come
from the completed `operator-batch-20260911T142353` capture, with explicit operator
HOME and wrist2-label corrections. Preserve source hashes and original records.
Keep bulk recordings, caches and run outputs removable under ignored `artifacts/`.
Keep fixture generators, replay launchers and fault injection under `tests/` or
the existing explicit `simulation/` path. Production adapters share the same
mapping, ownership, lifecycle, recording and verification code.

Replay cannot reproduce USB traffic, RealSense alignment cost, true concurrent
exposures, motor gravity/load or real device timing. Historical camera frames and
leader motion are unrelated captures: they test orchestration, not synchronized
demonstrations or visually consistent robot motion. Synthetic calibration images
are required where the recordings lack suitable board observations. Mac native
and Docker amd64 performance results must be reported separately from Ubuntu
hardware acceptance. Earlier failed combined-load runs remain failed evidence.

## Ordered nodes

Node numbers describe this execution sequence; they do not replace stable module
or acceptance IDs. Actual results are recorded below; the table defines scope.

| Node | Modules | Deliverable | Acceptance scope |
| --- | --- | --- | --- |
| N1 | M02, M04, M12 | Correct signed teaching coordinates; separate powered goal coordinates and coordinate epochs; retain the actual initial HOME sample; implement assigned lever OPEN=3256/CLOSED=3388 saturation; persist versioned calibration | M04-A03, M12-A05 software: continuous negative values, reset invalidation, immutable references, wrong/stale calibration rejection, endpoint saturation. Physical sign/scale/range verification remains open |
| N2 | M04, M06, M09 | Connect a replaceable leader source to the shared control session; nominal 60 Hz acquisition and existing 50 Hz command cadence; immutable episode-relative baseline; explicit fresh/no-new-sample/stale behavior | M04-A01/A03 software and M06-A01/A03/A04 simulation: no invented source sequence or refreshed receipt time; no accumulated episode offset; dropped, reordered, stalled and restarted sources; asymmetric and near-limit URSim motion |
| N3 | M04, M05, M06, M09 | Implement coordinated leader READY/HOLD lifecycle against a stateful fake motor transport; implement Hand-E command/feedback ownership with a local protocol fixture and explicit bypass; retain one control owner | M04-A02/A03, M05-A01/A02/A03, M06-A01/A02 software slices: safe transition ordering, torque-induced coordinate reset, no stale goal, arrival failure, elbow active-motion prohibition, gripper request versus measured state, no release on stop/fault. No physical load/holding claims |
| N4 | M07, M08, M09, M10, M11 | Integrate all three recorded RGB-D sources, replayed leader, live URSim feedback and fake/bypassed Hand-E into the shared session and MCAP; persist immutable baseline/calibration and per-source provenance | M10-A01/A02/A03, M11-A01/A02/A03: distinct raw input, mapped intent, sent target and measured feedback; source time versus replay time; honest clock domains/epochs; independently decoded RGB and exact depth; keyboard start/stop/HOME/discard/exit |
| N5 | M02, M10, M12, M14, M15 | Complete agreed calibration orchestration software and remaining interface contracts: checkpoint capture with two-second stationary dwell, leader activation/invalidation, verified transforms if published, bounded twin sink and disabled policy hooks | M12-A01-A05 software/simulation; M14-A01/A02 and M15-A01/A02 interface tests: failed capture preserves calibration, held-out geometry checks, absent/stalled observers do not acquire ownership or block recording. No Isaac scene, policy inference or new training-export feature scope |
| N6 | M06, M08, M09, M11, M13 | Run integrated fault campaigns, then a fresh 20 x 40-second acceptance batch; resume previously deferred replay/resource investigation for this workload | M06/M11 fault slices, M13-A02/A03/A04: recorder death, queue saturation, disk/write failure, leader timeout/reset, URSim disconnect, cancellation and recovery without automatic following; every accepted file independently audited; report CPU/RSS, source age, skew, queues, encode times and storage cost |
| N7 | M01, M13 | Rebuild a source-matched candidate image; installed Jazzy regression, launch/mount smoke and final-image integration checks; update module matrix and lab handoff | M13-A04 plus existing M01 delivery checks: image/source/dependency identity and reproducible commands; clearly separate PASS/FAIL/NOT RUN/BLOCKED. Promote the candidate only after its applicable gates pass; preserve the accepted current image otherwise |

## Contract decisions proposed for alignment

- Keep follower-HOME-anchored episode-relative mapping. A calibration reference
  and an episode baseline are distinct immutable records. Simulation signs and
  ranges are explicit test configuration, never proof of physical calibration.
- A control tick may observe no new leader sample. Specify bounded target holding
  using the original sample identity and acquisition age; do not fabricate fresh
  measurements to satisfy the controller. Stale input still faults under the
  existing bound. Test command records independently from source-sample records.
- Separate signed logical feedback from powered goals and invalidate baselines
  across coordinate transitions. ID3 remains prohibited from active physical
  motion; software tests cover that refusal and coordinated-READY blockage.
- Stub actuator dynamics only to test sequencing and failure handling. Verify
  actual register/protocol encodings against manufacturer documentation before
  implementing a transport; unresolved physical endpoint behavior stays explicit.
- Prefer running the full replay pipeline within one host clock domain. If a
  native-to-container bridge is necessary, define and test bounded clock mapping
  and discontinuity handling before using age gates across domains.
- In N6, retain the 16.7 ms matching gate and current approved acceptance profile.
  Do not loosen freshness, queue bounds or success criteria to hide Mac resource
  failures. If the Mac cannot pass full load, finish functional/fault gates and
  deliver a reproducible Ubuntu performance gate marked NOT RUN or BLOCKED.
- M12 physical board geometry, taught routes and accuracy thresholds remain
  configurable/unresolved; prioritize its software closure after the recording
  lifecycle. M14/M15 remain interface-only, as previously agreed.

## Delivery rhythm and remaining hardware acceptance

For each node, update the owning module plan before implementation, record its
actual test outcome afterward, and commit each coherent accepted increment.
Inspect the existing uncommitted leader work and include only reviewed changes;
do not overwrite or discard it. An aligned version of this cross-module plan
provides concrete scope authorization without requiring repeated routine approval.

Physical acceptance still requires leader direction/scale/ranges, powered
HOME/HOLD accuracy and support, resolved ID3 cable clearance, real Hand-E
actuation/contact/retention, real calibration imagery and geometry, and the full
Ubuntu workload with live devices. Previously accepted physical slices retain
their original revisions and scope. Only affected hardware gates need reopening.

Baseline before N1: native regression 363 PASS / 5 environment skips (9.95 s); Black and production/script Pylint PASS. The restricted sandbox run could not allocate shared memory; the unrestricted local rerun passed. No device was accessed. This baseline does not accept the new nodes. Its completion report must retain
every environment limit or failed gate rather than describing all modules as
physically accepted.

## N2 acceptance update

Shared source integration and conditioned-command recording: PASS in native
regression (369 tests, 5 environment skips) and an actual 8-second URSim replay
episode (240 image groups, stop/HOLD, independent audit). Black and production
Pylint PASS. Logs: `artifacts/offline-completion/n2-*`; actual simulator report
`artifacts/simulator-control/session-1789109729156955468/report.json`. Full
three-view recorded imagery and the new long batch remain N4/N6, not yet accepted.

## N3-N5 progress and resource evidence

Native regression before the final extra codec tests: 386 PASS / 5 environment
skips; production/script Pylint and Black PASS. Stateful motor/coordinator and
local Hand-E wire tests pass. N4 functional smoke with three recorded RGB-D
streams and actual URSim control completed an 8-second file and held review.
Its 230/240 grouping result fails the stricter quality gate; the runner's PASS
label describes its older smoke assertions, not a full M13 quality pass.

Serial amd64 encoding failed a bounded queue (59.5 ms/group). Three concurrent
camera encoder jobs reduced the average to about 22 ms in a later run, but
long-load stalls still failed recording. Increasing client memory from 2 GiB to
5 GiB did not establish a throughput pass. An internal Docker replay-cache volume
removes the host bind path for a separate comparison; it is removable test data.
No failed run is reclassified, and no queue/skew/freshness gate was relaxed.

N5 software checks cover leader configuration activation/invalidation, taught
checkpoint traversal, optional read-only twin events and disabled DAgger hooks.
Remaining image/release and long-batch results will be appended after execution.

N5 URSim traversal PASS: 20 taught checkpoints and 30 image/readback pairs in
`artifacts/simulator-control/calibration-1789110837993802217/`. Exact dwell and
actual readback assertions passed; image geometry remains a separate solver gate.

Reviewed N3-N5 commit baseline: **389 native PASS / 5 environment skips**
(10.12 s), Black PASS, production/script Pylint PASS, whitespace checks PASS.
Parallel/serial codec payloads are byte-identical in regression; injected codec
failures reap all encoding threads. Local trajectory export was verified against
an actual completed URSim/replay MCAP. New source-fault and full-load campaigns
remain N6; no throughput failure is hidden by this functional commit.


## N6 gates and repeated-load findings

N3 follow-up within the aligned stop/fault scope: an external fault during leader
HOME preparation or travel must request a fresh current-position HOLD, just as
an external fault during leading does. The previous leading-only failure branch
could leave a powered HOME goal active after closing its transport. Extend the
shared failure path to both HOME phases; retain strict fresh feedback and the
motor fault latch, with no guessed goals or automatic recovery. Holding/held
phases need no replacement goal. Leader HOLD is attempted even when closing the
follower transport raises. Stateful fake-motor cases cover both HOME phases,
fresh/stale feedback and cleanup errors: all eight new cases PASS, within 31
targeted session/motor tests. The actual URSim campaign adds a recorder failure during leader HOME;
that new case remains NOT RUN until the current batch finishes. No physical
motor transport or write is authorized. The frozen-image batch remains evidence
for its own revision.

The new leader fault campaign PASSes stale input, changed epoch, out-of-range
encoder values and recorder-process death on actual URSim. Each case archives
three seconds of post-fault readback, confirms stopped/unchanged tail posture and
rejects normal episode commitment. Evidence:
`artifacts/simulator-control/leader-faults-1789111015828397008/`. Its initial
`detected_s` field includes shutdown/release; the runner now names and measures
this interval `fault_and_release_s`, separately from its three-second observation.
It is not a pure first-detection or emergency-stop latency measurement.

Prefaulted Docker-internal real-image replay completed one strict 40-second
episode: 1,196/1,197 groups (99.9165%), one rejection, writer peak 4/16 and
maximum queue delay 105.3 ms. All depth hashes and RGB payloads verify. Evidence:
`session-1789111147726326930`. The 460,040,972-byte MCAP averages 11.50 MB/s,
about 431 MB depth and 20 MB RGB payload. This scene implies about 9.2 GB for
20 episodes or 41.4 GB/hour if sustained; these are extrapolations, not measured
long-batch totals. Source acquisition age p95/max was 7.49/13.42 ms in replay,
not a physical USB measurement. Maximum accepted view skew was 16.6923 ms.

A fresh 20-episode real-image attempt FAILed on episode 0: 1,188/1,196 groups,
72.3 ms first-anchor offset and producer lateness up to 133.6 ms. Evidence:
`session-1789111417406940222`; container observations are under
`artifacts/offline-completion/n6-container-resources.jsonl`. This repeats the
Mac sustained-load limitation. No gate is loosened. The strict audit now knows
original omitted source identities from the immutable replay manifest; it still
rejects newly missing/repeated replay anchors, boundary loss and rejection bursts
(12 focused tests PASS).

The first recorded-leader/synthetic-camera 20-episode attempt completed three
40-second episodes, then faulted on an input gap over 100 ms during episode 3
(`session-1789111515061668419`). It remains FAIL. Error messages now distinguish
reordering from an excessive interval and record exact gap/sequence values.
Both simulation input variants now use the same three-camera encoding jobs;
physical defaults remain unchanged. Fresh batch and installed-image checks follow.

N6 checkpoint regression: 393 native PASS / 5 environment skips (10.38 s),
Black PASS (149 files), production/script Pylint PASS. The replay identity/gap
audit has positive and adversarial tests. This commit accepts software changes
and records failed batch evidence; it does not accept the pending long batch.


### Separating image workload from historical delivery loss

Add an explicit test-only `uniform30` pacing comparison, alongside the default
original-timing replay. The original cache contains accepted payloads only; its
omitted source frames and historical delivery gaps can themselves violate the
new batch's first/last-anchor gate. The comparison emits the same real pixels at
30 Hz with declared synthetic view phases (0/4/8 ms), preserving original
acquisition provenance and assigning separate replay timestamps. It measures
codec/storage/control workload, not historical exposure or USB timing. It must
never replace or relabel the original-timing FAIL, nor claim live-camera quality.
Use the same 16.7 ms, 75 ms, queue, source-age and batch-quality gates. Record
which pacing was used in each immutable snapshot and independently measure RGB
re-encoding loss; no new visual-quality threshold is silently accepted.


N6 reviewed follow-up: 409 native PASS / 5 environment skips (11.29 s), Black
PASS (151 files), production/script Pylint PASS. Twelve added leader-HOLD cases
cover all held phases, duplicate/stale readback and measured arrival duration;
four pacing/quality cases preserve original identity and explicit timing modes.
The first installed-package batch completed seven 40-second synthetic-image
episodes, then FAILed on a 109.719 ms leader gap (sequences 6799 to 6820), above
the unchanged 100 ms gate: `session-1789112535942329628`. Its preceding failed
startup correctly rejected the earlier C207A0 latch; explicit local simulator
recovery was logged and never added to automatic session startup.

Real-image RGB comparison decoded all 1,196 frames per view against the exact
first-generation cache: mean PSNR 40.18/39.94/40.88 dB and minimum
37.13/36.66/38.62 dB for wrist/left/right. These measure a second H.264 generation,
not raw-sensor capture quality; no new quality threshold was assigned. Results:
`session-1789111147726326930/episode-0000/rgb-reencode-quality.json`.

The next explicit resource comparison reserves Docker CPUs 0-3 for official
URSim and 4-9 for the collector client. This is a local test setting on the
10-CPU Docker VM, not a new Ubuntu hardware constraint. Memory remains 5 GiB
for real-image replay. Restore the prior URSim CPU setting after the comparison.

Historical PC comparison comes from the supplied replay's `host-snapshot.txt`
and `workload-summary.json`, not a new SSH probe: Core Ultra 9 285, 24 reported
CPUs and about 62.25 GiB RAM. Its two 30-second read-only captures used serial
encoding, averaged 21.03/21.88 ms per group, peaked at one queued group, and had
28.23/30.91 ms maximum writer delay. Camera delivery maxima were 9.37-11.89 ms;
no camera sequence gaps/repeats were reported. Storage was 337.87/347.68 MB.
This is an older image and has no active leader/control workload. The present
Mac M5/16 GB runs both the amd64 collector and URSim inside a 10-CPU Docker VM;
neither CPU percentage nor replay RSS is a direct prediction for that PC.
The next Ubuntu gate must add actual leader acquisition and the current image
to live-camera load before accepting the full resource allocation.

The first-anchor comparison resolves one timing ambiguity: the failed original
replay scheduled its first wrist anchor about 72.212 ms after recording start
and delivered it at 72.325 ms. Its boundary failure was already present in the
recorded delivery schedule, rather than 72 ms of new encoder latency. The
separate later 134 ms producer lateness and 109.719 ms control-gap failures
still stand. The successful original run scheduled/delivered its first anchor
at 20.862/25.095 ms. These estimates use the recorded control wall-clock offset;
raw calculations are in `original-first-anchor-analysis.json`.


The CPU-partitioned 30 Hz real-pixel attempt captured 1,199 groups but FAILed
at the 25-second independent verification deadline (`session-1789113319719656088`).
The closed MCAP later verifies diagnostically, but its partial directory is not
renamed or accepted. Standalone one/automatic/one H.264 decoder measurements
were 20.75/20.36/20.01 s; profiling points to PNG decode/hash, not decoder thread
count. M11 now adds bounded parallel image verification under an explicit
snapshot setting, with all original deadlines unchanged. Native regression:
419 PASS / 5 environment skips; lint and format PASS.

The actual URSim fault campaign was extended with child-local ENOSPC injection,
a two-second writer stall that must overflow the unchanged bounded queue, and
leader torque loss in held review. Two focused fixture tests verify explicit
triggering and synthetic-only source composition. All seven actual URSim cases
PASS on installed candidate `5219105`: stale input, changed epoch, invalid
range, recorder death, disk-write failure, writer backlog and held torque loss.
Each includes three seconds of independent stopped-state observation. The held
fault preserves the preceding completed episode; other cases commit no episode.
Fault-and-release times were 0.001-1.644 seconds, separate from the observation
window and not a pure stop-latency measurement. No filesystem was filled and no
physical motor received a write. Log: `n7-expanded-faults.log` under the offline
artifact directory.

Candidate `5219105` installed Jazzy regression PASSes 422 cases / 2 host-only
skips (23.16 s); both host mount cases PASS separately (4.05 s). Independent
three-worker verification of the earlier failed batch's closed MCAP took 8.70 s,
versus about 20 s serially, with identical decoded counts and exact depth hashes.
This diagnostic does not accept its partial episode. A fresh full batch tests
the unchanged 25-second finalization deadline in normal session operation.

### N6 final full-load result

#### Confirmed cancellation deadlock and correction plan

Final-image HOME cancellation initially hung. A focused repeat with Python
stacks reproduced the owner blocked inside `multiprocessing.Event.set()` ->
`Condition.notify_all()` -> `notify()`, called by `Session.fail()`. A killed
recorder can leave the shared waiter's wake-up acknowledgement unconsumed.
The synchronous cancellation notification then prevents subsequent stop/HOLD
handling. Evidence: `n7-home-cancel-stress.log`. The intervening diagnostic
eight-case PASS is retained but did not establish a fix.

Within N6's recorder-death/cancellation scope, replace cross-process stop Events
with a monotonic shared-byte cancellation flag: initially zero, writers only set
one, no reset, lock, acknowledgement or coupled payload transfer. Waiters poll
locally at up to 5 ms intervals. Supported Mac/Ubuntu 64-bit hosts share this
single-byte state; no general lock-free multiword protocol is introduced. Apply
the same primitive to recorder, camera and read-only feedback shutdown. Keep
thread-local Events unchanged. Also make shared heartbeat-lock inspection
nonblocking, retaining the last observed timestamp rather than refreshing it
when the lock is busy. Reject an exited recorder before draining its messages.
Add real spawned-process killed-waiter tests and heartbeat-contention tests;
rerun the focused actual URSim cancellation campaign, complete fault suite,
native/installed regressions and affected final-image sessions before delivery.
No stop/freshness/quality deadline is increased. Targeted cancellation/session/
recording tests: 39 PASS. Full native regression: 431 PASS / five environment
skips (10.58 s); Black and production/script Pylint PASS. Four new tests cover
the killed waiter, surviving waiter, bounded cancellation, busy heartbeat lock
without timestamp refresh, and dead-process rejection before receiving replies.
The focused actual URSim repeat and final-image regressions remain pending.

The installed `5219105` candidate completed 14 strict 40-second real-pixel
episodes, then FAILed during episode 15 on a 155.436 ms leader interval
(sequences 2827 to 2856). Evidence: `session-1789114231754512844`. The requested
20-episode batch remains FAIL; six shorter or later episodes cannot complete it.
No threshold, queue, timeout or arrival tolerance was relaxed.

The completed subset had 16,794/16,799 accepted groups (99.9702%), with its
lowest episode at 99.8333%. It wrote 6,464,209,345 bytes, averaging 461.73 MB per
episode. Peak writer queue was 13/16; maximum writer delay 418.53 ms and maximum
replay delivery lateness 225.09 ms. Completed episodes had command gaps up to
70.21 ms and replay-source age up to 15.29 ms. Synthetic view phase was 8 ms
maximum by construction; this is not a new physical synchronization result.
Finalization completed within the unchanged deadline for all 14 files: elapsed
capture-plus-close time was 50.80-55.18 seconds for 40-second captures.

Twenty-four sampled resource observations saw up to 279.23% client CPU and
2.751 GiB client memory, plus 145.55% CPU / 1.386 GiB for URSim. Docker percentages
use one CPU as 100%; sparse samples do not prove peak instantaneous utilization.
The repeated 100 ms source/host gap failures remain unresolved on Mac amd64.
After the demonstrated codec improvement, further unchanged long-run retries
are not treated as a fix. Finish functional/fault/image gates and deliver the
unchanged full-load gate for Ubuntu, as authorized in N6. Preserve the failed
partial file and independently audit all 14 already committed files.

The subsequent HOME-fault correction `e06ca3a` passes 427 native tests / five
environment skips (12.31 s), Black (153 files) and production/script Pylint.
Its final-image checks exercise the changed fault path; it does not inherit a
20-episode throughput pass from this failed batch.
