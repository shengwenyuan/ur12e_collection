# M04: HOME-independent Relative Leader Input

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / hardware acceptance pending, 2026-10-06. The operator approved removing
fixed leader HOME requirements from relative teleoperation while retaining
joint order, directions, ratios, startup stability, input intervals, continuity
checks and follower protections. No motor writes or deployment are authorized
by this software implementation.

## Contract

Compute follower intent as its configured HOME plus signed, scaled encoder
counts relative to the last actual sample in the stable episode-start window.
Do not integrate per-step deltas, wrap counts or rebase after faults. Follower
HOME remains mandatory before engagement. Keep the existing 45-degree relative
gripper mapping and its separate input-rate guard.

Add a relative-input calibration document without leader HOME or fixed gripper
endpoints. Retain legacy fixed calibration documents for historical archives
and separate absolute-calibration workflows. New relative episode context must
not claim an absolute calibrated leader posture. Archive verification must
understand the new context and retain support for the old one. Configured input
intervals retain their existing numbers; inherited broad encoder intervals are
not newly accepted mechanical limits.

## Changes and acceptance

1. Separate count validation/difference from absolute HOME conversion.
2. Remove fixed-HOME equality from episode engagement; update archive audit.
3. Add HOME-free profiles to the native UR and Isaac example configurations.
4. Test identical deltas from different starts and fixed HOME definitions,
   HOME-free serialization/audit, unchanged follower HOME checks, invalid
   intervals, source resets/jumps, and gripper mapping.

M04/M09 software acceptance: PASS. Hardware/motion acceptance: NOT RUN.
Image deployment and powered leader force feedback are outside this change.
Force-feedback feasibility is discussion only and requires separate alignment.

## Acceptance results

Native Mac software checks: Black PASS; Pylint 10/10; full suite 734 passed,
5 skipped. Ten new cases cover direct count-delta equivalence with changed
legacy HOME values and different episode baselines, schema-4 serialization,
invalid configuration, follower HOME requirements, interval/epoch rejection,
and new/legacy independent archive audits with forged-intent rejection.

New examples use `config/gello.relative.json` (schema 4); legacy schema-3 files
remain readable. New episode context is version 2 and omits absolute calibrated
leader posture. Existing context version 1 remains verifiable. Gripper opening,
45-degree travel, jump/rate guards and follower motion limits are unchanged.
No physical connection, motor writes, image rebuild or remote deployment was
performed. Station-local configurations are not rewritten implicitly. A future
deployment must update executable code and explicitly select the relative
profile; old valid profiles still work with the new relative mapper.

## Force-feedback discussion, not implementation scope

UR RTDE provides `actual_TCP_force`; the collector does not currently subscribe
to it. This signal is distinct from recorded joint currents and requires a
verified payload, measurement reference and force/torque frame convention.
See the [official RTDE guide](https://docs.universal-robots.com/tutorials/communication-protocol-tutorials/rtde-guide.html).

XL430 supports PWM voltage output but not current-control modes. Present Load
is inferred, not a torque measurement. A limited resistance cue is more realistic
than calibrated torque reflection with the current leader hardware. See the
[ROBOTIS manual](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/).

Suggested progression: read-only wrench characterization, separately authorized
single-axis low-output resistance, then an independently reviewed bilateral
controller. Active feedback requires a new leader ownership path, mechanical
support, bounded outputs, stale-feedback handling, gravity/friction assessment
and closed-loop stability validation. No force-feedback mode is enabled here.
