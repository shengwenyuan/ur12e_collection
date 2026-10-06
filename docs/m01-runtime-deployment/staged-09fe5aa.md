# M01: Staged Flexlab Release 09fe5aa

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: software staging and activation PASS; hardware acceptance NOT RUN.

The operator requests delivery of commit `09fe5aa` while collection remains
active. Install source and image under revision-specific names only. Do not
retag `current`, modify the active checkout/configuration or launcher, stop a
container, prune images, or access hardware. Later activation and removal of
old versions require the operator to confirm that collection has ended.

## Observed station divergence

On 2026-10-06, `ur12e-collection` resolves to `ur12e-flexlab`. The active image
is `e98510ee47f8`, containing a station-side validator change, while its revision
label still names `0d38643`. Active station following limits are 48 deg/s and
60 deg/s2, with servoStop 0.4 m/s2; HOME remains 3 deg/s and 6 deg/s2. The
requested commit provides 24/30 following and 6/12 HOME. These are distinct
profiles; staging does not silently reconcile them or alter production.

The active leader profile is `gello.calibration-20261005.json`, with updated
encoder intervals. Preserve a station configuration snapshot separately from
the immutable source. Carry its signs, ratios and intervals into a HOME-free
candidate profile, without activating it. Candidate motion settings must match
the explicitly requested commit. Preserve station identities, camera setup and
task routes; do not use another station's settings.

## Delivery and checks

Reuse immutable cached dependency layers; build the wheel locally and install
it with no dependency resolution or network. Run installed-package integrity,
configuration and relevant software regressions in a CPU/memory-limited
container with no network or devices. Keep source/archive checksums and image
identity in a delivery receipt. Verify active image, process start time,
launcher and configuration hashes remain unchanged.

M01-A01/M01-A02 software staging: PASS. Production activation, hardware
acceptance and old-image removal: NOT RUN and intentionally deferred.

## Delivery result

- Source: `~/ur12e-releases/09fe5aa/source`, exact committed payload from
  `09fe5aae640e3e7685cbfc6b53f8a421a3ca3b9a`, plus isolated station-local files.
- Image: `ur12e-collection:09fe5aa`, linux/amd64, immutable ID
  `sha256:80cd4823c9ece85a156b450df83a616329f18989ae5fbf69558e2423185fc91b`.
- Reused every layer of the existing known dependency image
  `sha256:16f63391497fd9160618ed5f35b348ce80c790a7a0078a74721aa91985d94d9c`.
  No dependencies were downloaded. The first build used an unsupported local
  image-ID spelling in `FROM` and failed metadata resolution; using the existing
  tag after verifying its immutable ID resolved this. Both logs are retained.
- Installed-package integrity: all 122 packaged files match the wheel. Relevant
  installed regressions: 180 passed. Checks ran without network or devices,
  limited to 0.5 CPU and 1 GiB. Native full-suite evidence for the source remains
  738 passed / 5 skipped; the full suite was not repeated on the production PC.
- Candidate station/profile, camera metadata, task routes and HOME-free leader
  binding validate. Updated station encoder intervals are preserved. Candidate
  motion limits follow the requested commit, not the active station override.
- All 14 inspected active configuration/launcher files retained their hashes;
  `current` still resolves to `e98510ee47f8`. The active deployment and launcher
  symlinks are unchanged. Collector `62e6b487dabd` remained running across the
  staging checks. An earlier observed collector had already been replaced
  before the staging snapshot; this delivery issued no container stop/restart.
- No image tags were removed or promoted. Mac Docker was unavailable and was
  not needed; the small wheel was built from cached tools on Mac, then installed
  over cached PC layers.

PC evidence: `~/ur12e-releases/09fe5aa/receipt.json`, `installed-checks.log`,
`build.log`, source/context archives and SHA256 manifest. Local receipt copy:
`artifacts/deployment-09fe5aa/`. Station snapshots remain outside Git and the
image. The isolated candidate routes are under `source/config/local`; reconcile
the daily launcher's route selection when activation is authorized.

## Activation authorization, 2026-10-06

The operator confirms collection has ended and requests replacement, retaining
the previous version as `bak` without deleting it. Read-only inspection confirms
no collection container is running and all 14 active configuration/launcher
hashes still match the staging snapshot. Task routes match the new release.

Keep the old deployment at its original path to preserve absolute configuration
references; expose it as `~/ur12e-bak`. Tag the old current image as
`ur12e-collection:bak`, then promote the verified `09fe5aa` image to `current`
and atomically repoint `~/ur12e-current` to the staged source. Preserve the
station calibration entrypoint configuration. Verify launcher help, installed
package identity and active configuration without hardware or collection.
The previously reported rate difference is explicit: the activated version
uses following 24/30 and HOME 6/12 (degrees/s and degrees/s2 respectively).
Do not delete any prior images, source directories or recordings.

Activation PASS: `current` and `09fe5aa` both select image `80cd4823c9ec`;
`bak` selects the former `e98510ee47f8` image. `~/ur12e-current` now resolves to
`~/ur12e-releases/09fe5aa/source`, and `~/ur12e-bak` resolves to the untouched
`~/ur12e-real-teleop`. The existing `ur12e` launcher symlink follows `current`.
Its help and GELLO help commands pass. Rechecking the promoted image verifies
all 122 installed files plus station, camera, route and relative-leader bindings.
Calibration command configuration is preserved byte-for-byte. The task routes
match both deployments; no route override is necessary. Default recording root
remains `~/ur12e-data`, with the existing `--output` override available.

Only the separate URSim service was running after validation. No collection or
hardware control was launched; no prior image, source directory or recording
was removed. PC activation evidence is in `activation.json` and
`activation-checks.log` alongside the original staging receipt. Rollback must
restore both the deployment symlink and image selection together; the backup
directory alone does not select the backup image.
