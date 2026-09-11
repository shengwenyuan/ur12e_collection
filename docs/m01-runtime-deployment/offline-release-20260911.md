# Offline Completion Candidate Delivery

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned / implementing. This is N7 of the user-approved
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

M01-A01/A02/A03 and M13-A04: NOT RUN for the new image. Actual identity, installed
checks, archive checksum, cleanup outcome and remaining Ubuntu gates will be
recorded here after execution.


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

The final installed-package long batch is now running. The accepted current
image remains unchanged; this candidate is not promoted by the regression rerun.
