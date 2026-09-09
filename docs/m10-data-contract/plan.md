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

The Python contract slice is implemented. M10-A01.1 through M10-A03.1 passed software tests: distinct record kinds, immutable records, raw register range preservation, missing observations, explicit clocks/provenance, and rejection of non-finite joint values. Serialized samples include `kind` and `schema_version`. Full metadata snapshots, ROS schemas, and dataset integration remain pending and cannot be inferred from Python contract tests.
