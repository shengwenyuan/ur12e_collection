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
