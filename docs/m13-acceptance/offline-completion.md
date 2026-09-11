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
or acceptance IDs. All new acceptance below is NOT RUN.

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
