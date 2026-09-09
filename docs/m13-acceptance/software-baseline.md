# Accepted Camera-Only Software Baseline

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: accepted for the software/deployment scope below; physical-camera and
full-module acceptance remain open. On 2026-09-10 the user requested a commit of
passed scope so the next lab session can focus on unresolved physical evidence.
This closes an acceptance slice, not every requirement of its owning modules.

## Closed scope

| Stable cases | Accepted behavior | Evidence |
| --- | --- | --- |
| M01-A01, M01-A02.1-smoke, M01-A02.2, M01-A03 | Runtime imports, source-free deployment on the existing Ubuntu station, immutable image loading, non-root mounts and replacement persistence | Actual lab load/doctor plus both host mount tests |
| M07-A01/A02/A03 software slice | Persistent spawned sources, bounded queues/startup/cleanup, clock/counter checks and explicit source faults | Unit tests and persistent synthetic batches; physical SDK behavior remains open |
| M08-A01/A02/A03 algorithm slice | Nearest real candidates, 16.7 ms threshold, bounded waits, no accepted frame reuse, truthful timestamps and fault propagation | Existing matcher/recorder regressions and batch integration |
| M09-A04 camera slice | Receipt boundaries, asynchronous finalization, independent episodes, failure/partial preservation, no late commit and SIGINT cleanup | Lifecycle tests and actual subprocess/container interrupt |
| M10-A01/A02/A03 implemented contracts | Intent/command/feedback distinction, raw gripper units, frozen versioned snapshots, station/observation consistency and explicit simulation/uncalibrated context | Contract/snapshot tests and MCAP round trips |
| M11-A01/A02/A03, M11-A04 reader slice | Exact uint16 depth, independently decodable H.264 episodes, bounded writes and atomic completion, ROS CDR and native bag reader/playback | Unit tests, all-episode independent decoding and native ROS smoke |
| M13-A01/A02/A04 software slice | Camera-only entrypoint, structured timing/cost/error reports and explicit separation of simulated and physical evidence | Software batches and lab deployment record |

Current pre-commit check: Black passes; Pylint 10.00/10; 88 tests pass with four
intentional environment skips (two ROS checks and two opt-in Docker checks).
The prior Jazzy arm64/amd64 suites each passed 90 tests, skipping only the two
host Docker cases. Those host cases passed separately on the actual Ubuntu PC.
The [M13 plan](plan.md) and [lab record](lab-20260910.md) retain the detailed
commands, identities, earlier failure and successful rerun evidence.

The source-free Ubuntu runtime is
`sha256:8c393dd43cb8aaec6986489c0990a48aaf3f4eed43673b549b869de67563cbd2`,
delivered in `ur12e-shadow-bundle-20260910`. Before committing, all 22 installed
Python/schema files were compared with `src/ur12e_collection` by SHA-256 and
matched byte-for-byte. The existing image label `15c9d26-working-shadow` remains
historical; it is not relabeled as a clean commit. No runtime rebuild is needed
for this source/documentation commit. Disposable downloaded-data experiments,
recordings, and the separate M12 planning work are excluded from this commit.

## Next physical-camera session

Do not repeat dependency installation, the full unit suite, snapshot fixture
checks, synthetic lifecycle batches, codec fixture round trips or offline ROS
smokes solely because cameras are connected. The remaining cases are:

1. M07-A01/A02/A03: identify and bind wrist/left/right; verify actual RGB8 and
   aligned Z16 at 640x480 / 30 Hz, factory intrinsics/depth scale and original
   timestamps. Keep one physical pipeline per role across the batch.
2. M07/M08 physical integration: verify SDK global-time availability and assess
   comparable timestamps, startup behavior, observed rates/gaps/repeats and
   actual matching/rejection statistics. A software sanity check does not prove
   exposure synchronization or clock accuracy.
3. M11-A04 / M13-A02/A03: record twenty real 40-second episodes; measure real RGB
   quality and raw-depth compression, USB/CPU/queue behavior during capture and
   finalization, and sustained storage cost. Keep independent verification of
   each new real file enabled. This checks new data and end-to-end integration,
   not a repeat of the closed codec implementation acceptance.
4. M07/M09 physical cleanup: interrupt and disconnect a camera in separate runs;
   confirm SDK workers/devices release, only valid completed episodes survive,
   active work remains partial, and a fresh explicit restart works.

No motion is required. ZERO/READY, GELLO/Hand-E, keyboard leading/hold/discard,
calibration solving, LeRobot export and clean-machine M01-A02.1 acceptance remain
separate work; none is waived by this baseline. Camera cost/quality and clock
accuracy tolerances still require measured evidence and user alignment.

## Reopening rule

Reopen only affected software cases if code, dependencies, image, schema or
relevant configuration semantics change, or if a hardware failure implicates
that software. A commit does not exempt shared code from diagnosis. Otherwise
retain the closed results and spend lab time on the outstanding physical cases.
