# M02: Station Configuration Foundation

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Status: implemented / full-module acceptance pending (configuration slice)
- Module: M02
- Parent: [meta plan](../../meta_plan.md)
- Dependencies: M01; motion/visual calibration acceptance remains with M06/M12
- Updated: 2026-09-09
- Alignment: the user authorized the proposed M02/M10 minimal interfaces and station inspection order on 2026-09-09.

## Scope and design

Create one versioned JSON station document with explicit nulls for unknown device fields. The user confirmed `ur.host=10.18.1.106` for the UR12e controller on 2026-09-10; Hand-E server endpoint, unbound camera serials and motion configuration remain unknown. This documentation update does not write the live station configuration or change the generic example initializer. The three fixed camera roles are wrist/D405 and third_left, third_right/D435i or D435IF (the connected units report D435IF); profile is RGB8 plus aligned Z16 at 640x480 and 30 Hz. Initial maximum skew is 16,700,000 ns. GELLO is explicitly unavailable/stubbed. Unknown calibration and READY values must never become zeros or a ready state.

Provide `station validate FILE` for structural validation and optional camera-identity readiness checks. Use the same validation for atomic replacement. A temporary draft can contain null identities; a camera-ready check requires all three unique serials. This distinction never authorizes movement. An explicitly requested example initializer creates a new draft without overwriting an existing file. No hardware connection, automatic ZERO, camera start, or calibration occurs in these commands.

Keep the schema beside the installed Python package, with a sanitized example in `config/`. Validate finite numbers and reject unknown fields. Store real files only in ignored local configuration or the station host mounts. Future adapters compare observed identities to configured values; this first slice does not pretend to perform that hardware comparison.

## Steps and acceptance

1. Implement a strict shared schema, example creation, validation, and atomic replace helper.
2. Add CLI commands and tests, then update this plan with actual results.
3. Bind live identities after read-only inventory; physical startup checks remain pending.

| Case | Criterion | Environment |
| --- | --- | --- |
| M02-A01.1 | Wrong roles/models, duplicate serials, invalid profile, and non-finite values fail | Software fixtures |
| M02-A02.1 | Failed validation/replacement preserves prior bytes; example creation never overwrites | Temporary filesystem |
| M02-A03.1 | CLI and replacement use the same schema; draft and camera-ready checks are distinct | Software fixtures |

## Results and remaining work

The configuration slice is implemented. M02-A01.1, M02-A02.1, and M02-A03.1 passed local software tests on Python 3.12.13, including duplicate serial rejection, invalid profiles/NaN, interrupted replacement, and no-overwrite initialization. Camera identity checks against live inventory remain pending. The schema accepts explicit D435IF model names observed on the attached station. Full M02 acceptance additionally requires real identity checks, startup integration, and motion/calibration acceptance, all outside this foundation slice.

## Read-only integration increment

Optional station capture settings resolve to 75 ms wait and 1 ms polling and are validated against each new snapshot. Legacy stations and snapshots remain readable. No live station identity, HOME target or motion acceptance was changed. See the
[shared plan and results](../m13-acceptance/readonly-integration.md).


## Calibration configuration increment (2026-09-10)

The autonomous simulator sprint authorizes optional explicit setup declarations
and per-camera calibration results. Offline activation verifies copied evidence,
recomputes the solution and requires matching serial, base, mount and simulation
identity. Setup changes invalidate affected cameras. Uncalibrated legacy stations
remain valid and motion remains disabled. Station updates now serialize complete
read/validate/replace transactions using an advisory lock. A hard-link backup
restores prior visible bytes if replacement-directory synchronization fails.

M02-A02/A03 software portions PASS in M12 activation tests, including corrupted
inputs, failed fsync, immutable snapshots and moved-camera invalidation. Physical
mount verification and real startup/control acceptance remain NOT RUN.

### N5 leader calibration binding

Under the aligned offline completion plan, optional GELLO setup/calibration fields
now use the same serialized atomic station update path. Evidence hashes, assembly
identity, provenance and follower HOME are checked. A remount invalidates the
leader result without rewriting past episode snapshots. Software tests pass;
physical verification and motion activation remain explicitly false. Details
are in the M12 plan.
