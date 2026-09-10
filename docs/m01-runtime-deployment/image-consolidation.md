# M01: One Current Collector Image

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: consolidation accepted; eight early archives removed with user approval; old Docker-image cleanup still pending, 2026-09-11.

The user requested consolidation of current images and an explicit removal list
after verification. Use one current collector image for daily collection,
simulator clients and development tests. Preserve existing images until the user
reviews the concrete cleanup list. No lab access, device operations or motion
are needed for image consolidation. Control and normal capture semantics are
unchanged; the acceptance-found teardown correction is documented below.

## Decisions and scope

- `ur12e-collection:current` is the only ordinary collector default. It uses the
  existing development stage (runtime plus pytest/Black/Pylint and installed
  tests), linux/amd64, Ubuntu 24.04/Jazzy. The roughly 50 MB unpacked testing
  increment is accepted as a practical consequence of the requested single image.
  No Torch/LeRobot export environment, new compiler toolchain or URSim appliance
  is added. Preserve the smaller intermediate runtime build stage for layering;
  it is not a second daily image or release.
- Compose dev/station, physical camera launcher and simulator client use this
  default and one `UR12E_IMAGE` override. `--client-image` remains an explicit
  simulator override. Offline bundles pin an immutable image ID for both Compose
  profiles; the mutable current tag never changes an existing bundle's identity.
- Dev remains network-isolated; station networking/device boundaries and physical
  control prohibition remain unchanged. Do not start camera/control tests here.
- Official pinned URSim remains a separate simulator appliance and running
  container. Do not merge or alter its controller volumes/image. The pinned ROS
  base remains a rebuild dependency; it is not a collection application version.
- Refresh installed dependency manifests after test tools are installed. Preserve
  current code's exact package hashes and prior control/camera acceptance.
- Deliver one new immutable offline bundle, with a local `artifacts/releases/current`
  symlink for convenience. Do not overwrite old bundles, remove image tags, prune
  Docker caches, remove containers or delete volumes in this increment.

## Procedure and acceptance

1. Inventory tags/IDs/platforms, all container references, bundle manifests and
   active launcher defaults. Record old references before changing them.
2. Unify default selectors and amd64 build targets, document the current commands,
   and verify Compose dev/station resolution plus explicit overrides.
3. Build the single image, compare installed package hashes, check dependency
   manifests and non-root identity; run installed Jazzy tests and both mount tests.
4. Load and verify the new bundle, exercise its source-free network-isolated dev
   launcher, then point the local current-bundle symlink at the verified directory.
5. Record exact results under M01-A01/A02/A03 and list old tags/bundles/cache
   candidates. Historical reports retain their original image identities.

The inventory currently has nine project image tags, none used by any container;
the sole running container is the pinned official URSim. Docker reports shared
layers and an anomalous negative reclaimable image size; do not sum displayed
virtual image sizes or promise an exact cleanup saving from that report.

## Selector verification

M01-A02 software **PASS**: both resolved Compose profiles select
`ur12e-collection:current`, linux/amd64 and the development build stage. An
explicit `UR12E_IMAGE` override changes both profiles together. Dev remains
`network_mode: none`; station retains its existing host network. Launcher Python
lint passes at 10.00/10; shell syntax and formatting checks pass. Application
package sources are unchanged. Image/bundle acceptance remains pending below.

## Failed candidate and bounded correction

Candidate `82f199361dab` had 250 installed tests pass and one strict interrupt
case fail: expected camera shutdown raced an in-flight read and printed a false
worker failure. The candidate is **not accepted**. Source hashes, dependency
manifest and both mount tests passed, but those do not override the failed gate.
The existing race is corrected in M09 with three lines of cancellation handling;
normal capture/control remains unchanged. Native suite now passes 252 cases,
with deterministic fault-versus-cancel coverage and varied group-interrupt timing.
Preserve `artifacts/image-consolidation/installed-tests.log` as failure evidence.


## Cleanup proposal (not executed)

Keep `ur12e-collection:current`, official URSim image `39909bad9a82` and its
running container/five volumes, and ROS base `2589a8fba525` for offline rebuilds.
The following nine collector tags have no container users and are superseded:

| Collector tag | Image ID prefix |
| --- | --- |
| `dev` | `7445aaced3d8` |
| `shadow-arm64-dev` | `81bdb3eff25f` |
| `shadow-runtime` | `8c393dd43cb8` |
| `readonly-dev` | `35a6bdc4af43` |
| `readonly-runtime` | `7d3fdd1a9a8c` |
| `sim-dev-36c00b2` | `926d151fbc62` |
| `sim-runtime-36c00b2` | `dc43e74d822f` |
| `sim-dev-6e48d82` | `b6f5f246c8ab` |
| `sim-runtime-6e48d82` | `3165576f143d` |

Each tag belongs to `ur12e-collection`. After user alignment, remove only those
specific tags, rechecking container references first. Do not use broad image or
system pruning: the official pinned URSim may display `<none>` despite being
required. No old tags, containers or volumes were removed in this increment.

Nine old release archives total 4,244,685,312 bytes. Recommend retaining
`artifacts/releases/ur12e-simulator-6e48d82/image.tar` as one rollback artifact and
removing the eight older `image.tar` files (3,770,061,824 bytes, about 3.77 GB):

- `ur12e-foundation-bundle-20260909`, `-v2`, `-v3`;
- `ur12e-shadow-bundle-20260909`, `-v2`, and `ur12e-shadow-bundle-20260910`;
- `ur12e-readonly-bundle-20260910` and `-v3`.

Retain their manifests, dependency lists and historical reports; missing archived
image files must not be represented as complete loadable bundles. This proposal
remains unexecuted. Build-cache cleanup is optional and separate; it sacrifices
rebuild speed and is not required to establish one current application image.

## Final image acceptance

M01-A01/A02/A03 **PASS** for the consolidated image:
`ur12e-collection:current`, immutable ID
`sha256:a3d22d1ffa6c36331116a4c870f7bb841d84ec036cd9a2d23460345ce15bab96`,
source commit `bbc56a8c714e7a8bc1b6f9124af80339352a2b97`.
Native regression: **252 PASS / 5 environment skips**. Installed Jazzy suite:
**255 PASS / 2 host-only skips**. Both host mount tests separately **PASS**.
The failed predecessor was replaced; none of the prior nine project versions
was deleted. Real hardware and new motion acceptance were **NOT RUN**.


## Verified bundle and current selector

M01-A01/A02 **PASS**: all 59 Python/schema package hashes match the final code;
non-root linux/amd64 identity and complete installed dependency manifest match.
Both source-checkout and source-free bundled dev launchers pass software/mount
checks with no hardware/network access. The bundle overrides a deliberately
invalid `UR12E_IMAGE` with its recorded immutable ID, proving dev no longer uses
a separate stale image selector. No source overlay was used by installed tests.

New bundle: `artifacts/releases/ur12e-unified-bbc56a8/`.
Local convenience symlink: `artifacts/releases/current` points to that directory.
All 17 delivered file checksums pass; the real bundle loader loads the recorded
image ID successfully. Archive size: **485,872,640 bytes** (about 486 MB).
SHA-256: `b25853739e43ec35af0a7ec4cfafc653c83b8d7d924da8d71773a5f5847b0121`.
The previous runtime archive was 474,623,488 bytes; the unified test/tool image
adds about 11.25 MB to the compressed offline delivery. Docker's displayed
unpacked image size is approximately 2.07 GB and includes shared layers.

Final reproducible commands:

```sh
./scripts/run dev doctor --format json --require-mounts
# Run installed tests in the same current image, without devices or network.
docker run --rm --platform linux/amd64 --network none \
  --entrypoint /bin/bash -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  -w /opt ur12e-collection:current \
  -c 'source /opt/ros/jazzy/setup.bash && pytest -q /opt/tests -p no:cacheprovider'
```

Official URSim, its five persistent volumes and all nine previous collector tags
remain intact. The failed temporary consolidation candidate was superseded when
`current` was rebuilt; its failure log remains. No Docker prune or lab deployment
was performed. Current snapshots still distinguish physical, simulated and
unavailable devices; consolidation does not enable real control.


## Authorized archive cleanup (2026-09-11)

The user explicitly approved the eight early archive removals and retention of
`ur12e-simulator-6e48d82`. All eight named `image.tar` files are now removed,
totaling **3,770,061,824 bytes**. Their manifests/reports remain; each directory
has `ARCHIVE_REMOVED.md` marking it metadata-only and not a complete bundle.
The current and rollback archives passed SHA-256 checks before deletion and are
retained. Exact removed paths and byte counts are recorded locally in
`artifacts/lab-20260911/archive-cleanup.json`.

This approval did not include the nine Docker image tags, build cache, remote
historical bundles, containers or volumes; none of those were removed. Current
Ubuntu synchronization is recorded in M13 `lab-20260911.md`.
