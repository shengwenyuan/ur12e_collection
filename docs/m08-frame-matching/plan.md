# M08: Offline-Testable Wrist-Anchored Frame Matching

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Module: M08
- Status: implemented / live-clock acceptance pending
- Parent: [meta plan](../../meta_plan.md)
- Dependencies: M07 frame identity and timing; M10 provenance
- Updated: 2026-09-09
- Alignment: on 2026-09-09 the user approved the written M08 defaults and requested M08/M11 development with local tests; lab deployment is deferred until the next lab session.

## Scope

Implement a deterministic matching core that runs on Mac with no cameras, robot, SSH, or ROS graph. Feed explicit synthetic frame references or previously captured timestamp logs. This is the matching algorithm, not the live camera owner, image encoder, or episode writer. Synthetic inputs and outputs must remain explicitly labeled.

Use the confirmed three roles (`wrist`, `third_left`, `third_right`), aligned RGB-D input pairs, and maximum cross-camera color timestamp skew of 16,700,000 ns. For each wrist anchor, select the nearest eligible real frame from each third view. Compare timestamps on an explicitly declared common clock; preserve original color/depth source clocks and host receipt times. Spatial alignment does not establish temporal synchronization.

Hardware-clock values from separate devices are not directly comparable. Inputs without an established common clock fail explicitly. Offline fixtures can declare their clock; a real clock mapping and its validation remain an integration prerequisite. Historical SDK `global_time` logs can support exploratory analysis, not prove clock accuracy.

## Aligned decisions

1. Wait at most **50 ms** after the wrist frame's host receipt, using an injected monotonic clock. Finalize earlier when both third-view streams have advanced through the anchor time, making the nearest available candidates decidable. At the deadline, accept only if both candidates meet the skew and identity constraints; otherwise reject the group.
2. **Do not reuse frames across accepted groups.** Both color and depth identities must be new for every selected camera member. Preserve repeats in diagnostics; never duplicate an image to fill a missing observation. Candidate ties choose the earlier source timestamp. Process wrist anchors in order; this is an online greedy matcher, not global sequence optimization.
3. Bound each role's buffer to **8 frame references**. Overflow, expiry, missing views, reused depth, and excessive skew produce explicit reasons and counters. Never retain an unbounded queue or synthesize a replacement frame.

## Interfaces and steps

Frame references carry role, device identity, source generation, color/depth counters, separate common-clock color/depth times in integer nanoseconds, original time provenance, host receipt time, and an opaque payload reference. Group results contain either three real members and their skews or a rejection reason tied to the wrist anchor. Metadata retains original acquisition times; matching completion time is separate.

Expose a small push/advance/finish API with an injected current monotonic time. Source restarts or backward clock/counter jumps invalidate pending work and require an explicit new generation; they never silently resume an accepted stream. Finish resolves pending anchors against received frames and reports incomplete groups. No background thread, SDK import, hardware ownership, or filesystem writer is required.

1. Define frame/group records and validate role, clock, generation, and units.
2. Implement nearest-frame selection, bounded waiting/buffering, rejection reporting, and explicit generation reset.
3. Test deterministic synthetic timelines and replay available timestamp logs as diagnostic evidence. Record conclusions here before integrating with M07/M11.

## Acceptance

| Case | Criterion | Environment / current result |
| --- | --- | --- |
| M08-A01.1 | Every accepted group contains one real frame per role, anchored on wrist; ties are deterministic and no accepted color/depth identity is reused | Offline fixtures / PASS |
| M08-A02.1 | Inclusive 16.7 ms boundary, missing views, delayed arrivals, 50 ms deadline, and buffer overflow have deterministic outcomes and bounded storage | Offline fixtures / PASS |
| M08-A03.1 | Incompatible clocks, backward counters, and generation changes cannot create apparently valid groups; original times remain traceable | Offline fixtures / PASS |
| M08-A01.2 | Saved timestamp-log analysis reports startup/end losses, reuse exclusions, and rejection counts without claiming live synchronization | Local historical logs / PASS |

No hardware motion is required. Full M08 acceptance still needs live clock validation and integration with the persistent M07 camera owner. M11 encoding/storage and M13 shadow throughput will use this contract in separately aligned plans. Real UR/GELLO READY, Hand-E protocol, calibration geometry, and motion acceptance remain deferred until their prerequisites are available.

## Implementation and validation results

Implemented `matching.Frame`, `Match`, `MatchConfig`, and `Matcher`, with explicit source provenance, nearest eligible candidate selection, deterministic ties, inclusive skew limits, 50 ms waiting, eight-reference buffers, expiry/overflow counters, and non-reuse of color/depth identities. Source faults invalidate pending work and block further input until an explicit newer generation is supplied. Late arrivals cannot rescue an expired anchor. The implementation does not import an SDK or initiate network/hardware access.

On 2026-09-09, local Python 3.12 checks passed for ties, threshold boundaries, late/missing arrivals, repeated depth, overflow/end-of-input, incompatible clocks, source identity changes, and generation reset. Black and Pylint pass. M11 integration tests exercise actual matched groups and rejection records through the writer. The parent software suite has 48 passing tests; the Jazzy-only CDR case is skipped outside ROS, alongside two opt-in Docker persistence cases.

`replay_camera_timestamps.py` exercised the saved M07 `three-camera-warmed-40s-01` logs: 1200 wrist anchors, 1163 accepted groups, 36 without an in-window third-view candidate at decision time, and one rejected for frame reuse. Expired references are retired separately from buffer overflow. Every rejected anchor remains counted. Analysis role labels are placeholders because physical left/right binding is not yet supplied. The replay assumes SDK global-time comparability; these results do not validate physical synchronization or prove the cause of rejected groups.

Evidence is in ignored `artifacts/hardware/three-camera-warmed-40s-01/m08-matcher-report.json`. The source is based on commit `48ad1f7` plus this module working tree. Live clock mapping, startup readiness, persistent-source integration and lab throughput remain NOT RUN in this offline increment. Do not adjust the confirmed skew or invent frames to improve the acceptance count.

## Aligned review corrections (2026-09-09)

The user authorized implementation of review points 2, 3 and 4 and a tested
commit before planning further modules. This section is the primary cross-module
plan; M11 and M10 describe their storage/time interfaces. Snapshot construction
and encoder concurrency are explicitly deferred.

1. Share accepted-frame freshness rules between M08 and M11: strictly new color
   and depth identities, increasing depth time, and at least one microsecond
   between accepted RGB acquisitions (the current encoder time resolution).
   Bad candidates produce frame-reuse or invalid-timing rejections before
   encoding. Keep source discontinuities separate from these local exclusions.
   Pass one MatchConfig to matching and recording; persist it for verification.
2. Always raise a typed SourceFault on a source discontinuity, carrying the
   rejected pending anchors and current generation, including when that list is
   empty. Block until explicit reset to a newer generation. M07's future rig
   owner allocates generations and establishes readiness; M09 owns episode
   failure/restart policy and invokes M06 for stop/hold. No automatic following
   restart and no persistent-source implementation are added here.
3. M11 uses a strictly increasing ordered log timeline: each log_time is the
   maximum of its acquisition time and the preceding log_time plus one ns.
   This is an ordering coordinate, not measured disk-write time. Exact mapped
   acquisition times remain in publish_time, ROS headers and group provenance.
   Snapshot and group metadata therefore precede their observations in both
   file and log-time order, even with skew or late control records.

Validation: add composed M08-to-M11 bad-depth/recovery cases, non-default skew,
sub-microsecond rejection, uniform faults with/without pending anchors, reset
isolation, and positive/negative image skew plus late control/rejection records.
Run the complete native suite, formatting/lint and available local Jazzy checks.
These extend M08-A01.1/A02.1/A03.1 and M11-A02.1/A03.1/A04.1; hardware acceptance
and real replay remain pending. No robot motion or lab connection is required.

### Correction results

PASS on 2026-09-09: M08-A01.1/A02.1/A03.1 now include composed recording
regressions for stationary/backward depth timestamps on every role, recovery
without episode failure, sub-microsecond RGB exclusions, non-default skew,
source faults with and without pending anchors, and generation-isolated reset.
Five seeded arrival/skew timelines each account for all 60 wrist anchors and
check every accepted group against the recording contract. Ordinary invalid
candidates are excluded before encoding; source faults consistently carry their
pending rejections in SourceFault. Runtime recovery ownership is documented but
remains future M07/M09/M06 implementation.

The complete native Python 3.12 suite passed 66 tests with three environment
skips; Black and Pylint (10.00/10) passed. The local arm64 Jazzy image passed 67
tests with two Docker-in-Docker skips; the two opt-in Docker persistence tests
passed separately from the host. See M11 for image identity and fixture evidence.
No lab access or motion occurred. Live-clock and persistent-source acceptance
remain NOT RUN.

## Live grouping diagnosis (2026-09-10)

After direct USB connection removed observed D405 source discontinuities, two
40-second recordings still rejected 213 and 82 wrist anchors. See the
[timing diagnosis and proposed correction](timing-diagnosis.md). The user requires
resolving grouping and aligning timing/concurrency changes first. The 50 ms wait,
16.7 ms skew and implementation are unchanged; hardware acceptance remains open.

The user subsequently aligned the diagnostic/correction experiment scope.
[Results and resource gates](resource-gates.md) remain subject to final settings
alignment. A bounded M09/M13 end-drain correction and targeted physical-timing /
depth-integrity regressions are implemented under the diagnosis plan; runtime
wait/poll/codec default changes remain experimental until that final alignment.
