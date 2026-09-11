# Offline Completion Candidate Delivery

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / local candidate verified; Ubuntu acceptance pending. This is N7 of the user-approved
[offline completion plan](../m13-acceptance/offline-completion.md).

## Scope and checks

Build one linux/amd64 collector candidate from the reviewed source revision using
the existing development target: Ubuntu 24.04, ROS 2 Jazzy and the pinned official
ROS base digest `2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4`.
The image contains the runtime, test dependencies and `/opt/tests`; it does not
contain recordings, station identities, credentials or the local Python venv.
Official URSim 5.22.2 remains a separate unchanged image/service.

Run native regression/lint, installed Jazzy regression, both host mount tests,
and final-image actual URSim session/fault checks. The new
`scripts/sim_control.py --installed-package` first compares every installed
Python/schema hash against the reviewed source, then uses the installed package
without mounting `src` or setting its import path. Check scripts remain frozen
test fixtures. This distinguishes an image gate from development-overlay tests.

Package the immutable candidate using `scripts/release.py`; check all delivered
checksums and the image manifest, source identity, dependency lists, loader and
source-free doctor entrypoint. No lab SSH, physical probe, device mount or physical
control is part of delivery. The candidate must retain real-image throughput
FAIL/BLOCKED if the Mac cannot pass the complete workload. In that case preserve
the accepted `current` selector and deliver the candidate for explicit Ubuntu
acceptance; do not silently promote it as a passed production release.

## Authorized cleanup and rollback

After the replacement candidate passes its software/image checks, remove the
clearly superseded local `ur12e-collection:gello-development` image. Preserve
the accepted `ec64004` image/current selector, official URSim and its volumes,
the pinned ROS base, and the explicitly retained `ur12e-simulator-6e48d82`
archive. Do not prune unrelated images, global caches or volumes. Temporary
recording/cache outputs remain removable under ignored `artifacts/`; any removal
must leave meaningful failure reports and source provenance intact.

## Acceptance results

The chronological candidate records below preserve failures. The latest candidate
section identifies the deliverable; earlier candidates are not additional daily
images. Ubuntu hardware acceptance remains separate from local image tests.


### First candidate checks

Built `ur12e-collection:offline-1ab61d7` from commit `1ab61d7`, image ID
`sha256:f4b9e1b87717ac20b80b3c105e3860d206eb6a49413dc6e0597ff348a04c218c`.
Both host mount tests PASS (4.20 s). The first installed regression FAILed with
a 15-second Ctrl+C exit timeout in the synthetic shadow test (395 PASS, 2 skips,
1 failure). An isolated recheck, 15 diagnostic repeats and 100 further diagnostic
repeats all PASS; a subsequent full installed run PASSes 396 tests / 2 host-only
skips (23.08 s). No cancellation code or timeout was changed to obtain the
passes. The original intermittent failure remains unexplained and is recorded
as an open reliability item, not a proven fix. Logs are under
`artifacts/offline-completion/n7-installed-*` and `n7-interrupt-*`.

This candidate's long batch failed after seven complete episodes on a 109.719 ms
leader gap. The accepted current image remained unchanged; the regression rerun
did not promote this candidate.


### Updated HOLD-supervision candidate

Candidate `ur12e-collection:offline-3cd7713` is built from commit `3cd7713`, image
ID `sha256:a22deef2cb47a0c651aaab767cd7f33b8a2c4690ceb21549f31f54b675e78924`.
Native regression PASSes 409 cases / 5 skips. Installed Jazzy regression PASSes
412 cases / 2 host-only skips (24.14 s), with both host mount tests separately
PASS (4.15 s). No source overlay or diagnostic signal handler was used in that
installed regression. Its two-episode real-pixel smoke passed; its 40-second
batch attempt failed at the 25-second verification deadline. It is superseded
by the bounded parallel-verification candidate below.

### Parallel-verification candidate

`ur12e-collection:offline-5219105`, source `5219105`, image ID:
`sha256:ca20d19738af32787ad1a2f6c3a16164132b489634ef74ad9f3e44f1ae930c36`.

- M01-A01 software PASS: 419 native tests / 5 environment skips; installed
  Jazzy regression 422 PASS / 2 host-only skips (23.16 s). Black and production
  plus script Pylint PASS. Installed tests use the package inside the image.
- M01-A03 local mount tests PASS: both cases (4.05 s), including persistence
  across container replacement. This is not a new Ubuntu device deployment.
- M13-A04 installed-source identity and seven-case actual URSim source/recorder/
  held-leader fault campaign PASS. Recorded trace and fixtures are external
  immutable test inputs; no production source overlay was used.
- M13-A03 fresh real-pixel 20 x 40 workload: FAIL after 14 completed episodes,
  then a 155.436 ms leader gap. All previous failures remain in the M13 record.
- This image is superseded by the HOME-fault correction below and is not packaged.

### HOME-fault candidate

`ur12e-collection:offline-e06ca3a`, source `e06ca3a`, image ID:
`sha256:ab4470390249f0335f281f4d5e580df915c2d3ffc8dcf652fdda05c6b31ae1c9`.
It additionally requests leader current-position HOLD if coordinated HOME is
interrupted, even when follower transport cleanup fails. Native regression:
427 PASS / 5 environment skips (12.31 s); lint/format PASS. Installed regression
430 PASS / two host skips (26.96 s), and both mount tests PASS (4.28 s).
The new HOME-recorder-death case exposed a cancellation deadlock. A focused
repeat captured `multiprocessing.Event.set()` waiting for a killed process's
wake-up acknowledgement. This image is superseded, not delivered as a fix.

### Cancellation-corrected candidate

`ur12e-collection:offline-b497c74`, source `b497c74`, image ID:
`sha256:5b5c44e037e91609347365f9d2e4cdd41072654fbdbbec2bb9801a4174ac671a`.
Cross-process cancellation no longer waits for worker acknowledgements; heartbeat
inspection cannot block the control loop on a busy shared lock. Native regression
431 PASS / five environment skips (10.58 s), including killed-waiter and heartbeat
contention cases; Black (154 files) and production/script Pylint PASS.
Installed regression: 434 PASS / two host-only skips (23.23 s); mount tests
2 PASS (3.27 s). Thirty focused HOME-recorder-death repetitions and all eight
fault cases PASS. Actual active discard, recorder loss, SIGINT, complex motion,
native HOME and optional ROS-observer loss also PASS. The native HOME observer
fixture required a recipe correction; production source was unchanged.

### Delivery image

`ur12e-collection:offline-39ad84b`, source `39ad84b`, image ID:
`sha256:9e37c327c7556abbc2d16c5723dcac0203bbbbab690276ff245989a8acfbb09a`.
This includes the corrected HOME test fixture. Every production Python/schema
file matches both `b497c74` and the working tree byte-for-byte, verified by
`scripts/release.py` source hashing. Installed regression: 434 PASS / two
host-only skips (23.68 s); two final-image mount tests PASS. The new image has
no production-code difference from the fault/motion-tested candidate above.
Final full-load acceptance FAILs after 13 complete 40-second episodes on a
114.276 ms leader interval above the unchanged 100 ms gate. All 13 completed
files independently pass decoding, exact depth, metadata, command and quality
checks; they do not satisfy the required 20-episode batch. Final-image SIGKILL
and SIGSTOP watchdog checks PASS with observed stops in 0.447 s and 0.251 s,
respectively, zero observed hold drift and rejected reacquisition during the
latched protective stop. See M13 for the complete evidence and retained failures.

N6 full-load acceptance remains BLOCKED for production pending an unchanged
20 x 40 run on Ubuntu with live inputs. The Mac attempt remains FAIL; a fresh
image tag does not reset it or establish new performance evidence. All agreed
software/fault slices can still be checked and delivered as an explicit candidate.

The accepted `current`/`ec64004` selector and bundle are preserved. Only this
latest candidate is packaged for the next explicit lab acceptance; official
URSim remains a separate appliance.

### Verified bundle and cleanup

The immutable local bundle is
`artifacts/releases/ur12e-offline-39ad84b`, with source revision `39ad84b`
and the delivery image ID above. Its `image.tar` is 486,388,224 bytes
(463.86 MiB), SHA-256
`210e11fec6610a76d7b6bf43e50a2dfc1793b0ebe3e494814f8c4e234cf7a554`.
It includes the image, manifest, package lists, launchers, configuration example
and capability/calibration/read-only/lab-return documentation.

- M01-A01 local delivery PASS: the actual `./scripts/load-release` verified
  all checksums, loaded the archive and checked its image identity.
- Source-free startup PASS: from the bundle, `./scripts/run dev doctor
  --format json --require-mounts` reported `software_ready: true`, all required
  dependencies available and both writable mounts available. An intentionally
  nonexistent `UR12E_IMAGE` environment value verified that the bundle manifest
  selects its packaged image. This fake-backend check has no hardware network
  or device access and reports hardware as not checked.
- Cleanup PASS: removed six unused, superseded collector images:
  `gello-development`, `offline-1ab61d7`, `offline-3cd7713`, `offline-5219105`,
  `offline-e06ca3a` and `offline-b497c74`. Their complete IDs and Docker removal
  results are retained in `artifacts/offline-completion/n7-image-cleanup.json`.
  No container referenced these images. No force removal or global prune ran.
- Preserved the latest candidate, the single accepted image carrying both
  `current` and `ec64004` tags, the pinned official ROS base, official URSim,
  all volumes and release archives including `ur12e-simulator-6e48d82`.
  The `artifacts/releases/current` link still selects `ur12e-unified-ec64004`.
- URSim remains healthy with a stopped program and NORMAL safety after explicit
  local recovery. Its full current CPU availability is restored as `0-9`;
  no test client remains. No physical control signal or lab SSH was used.

Delivery logs are `n7-release-load.log`, `n7-bundle-doctor.json` and
`n7-bundle-summary.json` under `artifacts/offline-completion/`. The subsequent
documentation-only commit does not change the image's runtime source identity.
Next action: explicitly synchronize this candidate in the lab, run the
[return sequence](../m13-acceptance/lab-runbook.md), and retain the same full-load
thresholds for a fresh Ubuntu live-input batch before production promotion.

## Lab synchronization: 2026-09-12

The user returned to the lab and authorized candidate synchronization, followed
by alignment of the next tests. The existing station `ur12e-collection`
(`ur12e-flexlab`, x86_64, Ubuntu 24.04.3 LTS, Docker 29.4.0) received the complete
bundle at `/home/robot2026fall/ur12e-offline-39ad84b`. Local development data and
`config/local` were excluded from transfer.

M01 existing-station delivery PASS: all delivered checksums passed, the archive
loaded with the expected image identity, and source-free `dev doctor` reported
all dependencies and both persistent station mounts available with
`software_ready: true`. This used `network_mode: none`, no device mappings, and
the existing `/var/lib/ur12e-collection` configuration/data directories. It did
not open cameras, serial ports, UR or Hand-E connections. The station JSON hash
remained `17c3b9e2e505972f90a2dc0add6ea64f23cdd830dda1154f60c015b24424bb9c`.

The accepted `current` image and `/home/robot2026fall/ur12e-current` link remain
on `ec64004`; use the candidate's own launcher for its acceptance tests. This
delivery does not promote a passed production release, establish a clean-machine
installation, or resolve the Mac full-load failure. No hardware test was run.
Evidence: `artifacts/lab-deployment-20260912/before.txt` and
`load-and-doctor.log`. Next proposed test is a short three-camera plus physical
leader read-only acquisition workload, followed by separately aligned powered
hardware and fresh 20 x 40-second acceptance stages in the lab runbook.
