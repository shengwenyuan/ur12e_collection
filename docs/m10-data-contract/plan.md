# M10: Single-Arm Data Contract Foundation

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Status: implemented / full-module acceptance pending (Python contracts)
- Module: M10
- Parent: [meta plan](../../meta_plan.md)
- Dependencies: none
- Updated: 2026-09-09
- Alignment: the user authorized the proposed M02/M10 minimal interfaces on 2026-09-09.

## Scope and design

Define stable camera roles, six UR joint names/order, schema version, source timestamps with explicit clock domains, host monotonic receipt times, and separate immutable leader-intent, sent-command, and actual-follower sample types. Joint positions use radians. Robotiq request/actual position remains raw integer data; missing values remain null. Preserve auxiliary registers separately when available rather than normalizing them.

Samples retain sequence, source identity, and an explicit simulated flag. A GELLO stub returns unavailable and cannot be mistaken for actual feedback or make a real controller ready. Do not invent a control frequency, interpolate values, infer clock correspondence, or implement ROS topic publishers, training projection, dataset writing, or DAgger behavior in this slice.

## Steps and acceptance

1. Implement concise typed contracts and validation, avoiding a generic event framework.
2. Add focused tests for semantic separation, raw value preservation, units/order, non-finite values, timestamps, and explicit missing data.
3. Extend the versioned contract when device evidence establishes additional fields.

| Case | Criterion | Environment |
| --- | --- | --- |
| M10-A01.1 | Leader intent, sent commands, and actual feedback are distinct types | Software |
| M10-A02.1 | Raw gripper values survive unchanged; missing feedback remains null | Software |
| M10-A03.1 | Source clock/identity, receipt time, sequence, and simulation provenance survive serialization | Software |

## Results and remaining work

The Python contract slice is implemented. M10-A01.1 through M10-A03.1 passed software tests: distinct record kinds, immutable records, raw register range preservation, missing observations, explicit clocks/provenance, and rejection of non-finite joint values. Serialized samples include `kind` and `schema_version`. M11 now preserves these records in ROS 2 CDR String envelopes under `leader/state`, `control/command`, and `follower/state`, with explicit per-episode snapshots. Typed live ROS publishers, auxiliary device fields, and training/dataset projection remain pending. M11 tests independently preserve missing follower joints and raw gripper values.

## Recording time contract (aligned 2026-09-09)

The user authorized review corrections 2-4. M11 preserves exact mapped
acquisition time in MCAP publish_time and image headers/provenance. MCAP log_time
is an ordered timeline, computed as max(acquisition_ns, previous_log_ns + 1),
including metadata, images, rejections and control records. It represents record
ordering, not a new exposure time or measured write time. Consumers use retained
acquisition fields for synchronization/training and log_time for ordered replay.
Snapshot and group context precede their payloads without equal-time ties.
This does not change original device clocks, receipt clocks or wrist anchors.
The snapshot schema and runtime builder remain a separate alignment item.


PASS locally: M10-A03.1 is exercised through corrected M11 files with signed
camera skew, independent depth times, and late control records. Both MCAP
reading orders preserve original acquisition fields and context association.
Live ROS publication and training/export timestamp policy remain unimplemented.

## Snapshot increment (aligned 2026-09-09)

Implement a versioned snapshot schema and builder for the user-approved M13
batch. Reuse M02 station validation; include station configuration, observed
camera identities/models, depth scale/intrinsics, explicit clock basis/validation
status, software revision and task. Require observed/configured identity agreement.
M11 freezes and validates the same schema; fixtures use the builder. Calibration
remains the explicit station value (currently null). M10-A03 adds round-trip,
mutation isolation, schema-version, identity, finite-value and mismatch tests.

Snapshot increment PASS: the shared schema/builder serves synthetic fixtures and
the M13 runtime; version, camera identity/model, finite intrinsics/scale and
simulation mismatches fail explicitly. Inputs are copied, and M11 validates the
same contract. Native/Jazzy round trips pass. Calibration remains null; live
factory readback and physical calibration validity await the lab.


The 2026-09-10 [software baseline](../m13-acceptance/software-baseline.md) closes
the tested software slice of this module. Remaining hardware or unimplemented
full-module cases stay open; repeat software checks only for affected changes
or new failures.

## Read-only integration increment

New ur_feedback and hande_feedback records share follower/state while retaining independent identities and clocks. MCAP feedback publish_time explicitly maps host receipt to Unix; controller uptime and Hand-E polling intervals remain separate. This is observation data with no fabricated action. The snapshot declares read-only sources, timing basis and effective camera settings. See the
[shared plan and results](../m13-acceptance/readonly-integration.md).


The 2026-09-10 [simulation-session increment](../m09-session/plan.md#autonomous-simulation-session-increment-2026-09-10)
extends control provenance and authority events with independent MCAP verification.
It preserves read-only validation and raw/missing gripper semantics.


The controlled recording slice passes actual URSim short/40-second episodes,
independent MCAP decoding, distinct intent/sent/actual values, authority boundaries,
and absent Hand-E fields. Mac/Ubuntu tests pass; no physical control acceptance
is implied. M11's optional projection preserves original integer clocks beside
LeRobot's explicitly nominal 30 Hz playback clock. See M09 and M11 detailed results.


M12 now contributes optional immutable per-camera calibration results. Snapshot
validation requires matching declared setup, simulation flag, device serial and
observed RGB optics. Old snapshots retain their original result copies when the
station's mount generation changes. Software tests pass; physical calibration
accuracy is not inferred from metadata consistency.

## Controlled-stream completeness audit

Require every controlled stream to span its authority interval within the shared
250 ms freshness tolerance, with no internal receipt gap above that bound. Paired
UR/follower records must be complete at finalization, including the final pair.
This closes a verifier gap where one early state plus a much later release could
otherwise look structurally valid. The bound is an optional explicit snapshot
field with a backward-compatible 250 ms default. It does not interpolate or
manufacture missing records. Test missing final UR pairs, long interior gaps,
missing tails and completed simulator episodes against the stronger validator.

Completeness checks PASS for missing final pairs, missing interval tails and long
internal gaps. A completed actual 40-second URSim episode (1,200 triples, 1,946
intent/sent pairs) also passes independent full-file verification with the stronger
validator. Full Mac suite: 232 PASS / 4 skipped, Black/Pylint PASS.

## Gripper training simplification (2026-09-11)

Aligned with the user: use one gripper closure scalar for the initial model,
0 fully open and 1 fully closed. Record raw POS and request/intent separately;
normalize only in training projection. Observation uses actual POS, action uses
the mapped leader request. Speed, force and other raw registers may remain as
auxiliary diagnostic data; they are not required model inputs or outputs in
this scope. Fault/validity still affect data eligibility. Endpoint mapping and
normalization need a versioned contract, with distinct measured-position and
command ranges where appropriate. Do not freeze the observed POS range 3-249
as calibrated endpoints or fill missing positions with zero. This is semantic
alignment only; no schema, runtime or exporter implementation changed here.

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


### Native physical recording increment, 2026-09-13

See [M09 physical recording](../m09-session/physical-recording.md). Snapshots now
explicitly accept real UR/URCap with station-bound identities. The acquired event
includes the relative gripper baseline; independent validation reconstructs raw
arm and gripper intent. Preserve separate 120-Hz command, 125-Hz UR and roughly
10-Hz raw Hand-E streams. SentCommand does not fabricate asynchronous gripper
acknowledgment. Snapshot inputs include transport, limits, guards and raw tool
speed/force configuration. Numeric flange reconstruction remains NOT RUN pending
active TCP-transform confirmation; base-to-active-TCP observations are unchanged.
