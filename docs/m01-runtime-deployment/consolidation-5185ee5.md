# M01: Unified 5185ee5 Deployment

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: accepted and promoted on both hosts, 2026-09-12.

The user approved consolidating the collector at exact source revision
`5185ee5b3dd2f8024af66a8409cfae3c8bf9ef65`, reusing existing local image layers
without downloading dependencies again, and matching local Docker and Ubuntu PC
images. Isaac Sim, its environment and scene assets remain separate.

## Delivery plan

1. Freeze the committed source and inventory existing image dependencies. Reuse
   cached layers and installed locked dependencies; build without external
   network access. Retain the existing Ubuntu 24.04 / ROS 2 Jazzy / Python 3.12
   baseline and non-root runtime. Include development checks in the unified image.
2. Verify installed source hashes and exact dependency versions. Run installed
   software tests without hardware or network. Preserve any failed results.
3. Assemble a checksummed release with launchers, manifests and committed
   configuration. Transfer to the PC, verify checksums, load that exact image
   and repeat installed software/mount checks with no hardware access.
4. Promote `ur12e-collection:current` and the existing native simulator selector
   to the same immutable image on both machines. Update the current release
   pointers only after verification; retain the old release for rollback.
5. Keep station settings, recordings and external Isaac untouched. No physical
   or simulated motion is started by deployment. Record source/image identity,
   cache reuse, test results and final cross-host equality here.

## Acceptance

M01-A01: identical platform, image ID, committed source identity and installed
source hashes on both hosts; no dependency downloads.
M01-A02: installed offline checks pass on the new unified image.
M01-A03: release checksums and source-free launchers pass with existing mounts;
station configuration remains unchanged. No new hardware acceptance is claimed.

## Results

**PASS — M01-A01:** both Mac Docker Desktop and `ur12e-collection` resolve
`ur12e-collection:5185ee5`, `ur12e-collection:current` and
`ur12e-collection:native-isaac` to exactly:

`sha256:dfd2d3a8209728ed52490d08da90cc4cdfeb5c5fb916db70fef8e7bf35dbdc0b`.

The source label is the full committed revision
`5185ee5b3dd2f8024af66a8409cfae3c8bf9ef65`. All 93 installed Python/schema
files match that frozen source and the release manifest on both hosts.
The image is linux/amd64, non-root `collector`, Ubuntu 24.04 / ROS 2 Jazzy,
Python 3.12.3. All 34 applicable runtime/development dependency pins match on
both hosts. Complete OS and Python inventories accompany the release.

**PASS — offline dependency reuse:** inherited the already installed development
dependencies from image
`sha256:80ac995dacda2403bd5815a5c2355cd63db48ac1366f62751fe6e4f112c2c508`.
Built the exact committed pure-Python wheel with `uv build --offline` using its
existing cache. The final image build used `--network none --pull=false` and
`pip --no-index --no-deps`; it replaced the application wheel and installed test
fixtures while retaining OS/runtime dependencies. Old installed tests were
removed before copying the committed suite. No dependency downloads occurred.
The release includes `BUILD.cached.Dockerfile` and cached-base provenance.

The initial standard-Dockerfile attempt missed its installation-layer cache
under disabled networking and failed apt resolution. Its log remains recorded;
it did not download dependencies. The initial uv call lacked cache permissions;
the authorized offline retry passed. macOS rsync rejected `--info=progress2`;
plain `rsync -az` completed the transfer. These initial failures are not passed
checks or hidden software fixes.

**PASS — M01-A02:** installed, source-overlay-free tests inside the exact image:

| Host | Result | Duration |
| --- | --- | --- |
| Mac Docker, linux/amd64 | 487 passed, 2 skipped | 22.68 s |
| Ubuntu PC | 487 passed, 2 skipped | 12.77 s |

Both runs used no network or device access, non-root execution, a read-only
container filesystem and temporary shared-memory/test storage. These results
are software acceptance, not new hardware or throughput measurements.

**PASS — M01-A03:** all 200 release file checksums pass locally and on the PC.
The verified loader imported the expected image. Manifest-bound collection
launchers and config/data mount checks pass on both hosts. The canonical PC
release also loads both native launcher help entries without starting the
leader, simulator or a control connection.

Station configuration SHA-256 remains unchanged:
`17c3b9e2e505972f90a2dc0add6ea64f23cdd830dda1154f60c015b24424bb9c`.
Doctor reports `software_ready=true`, `hardware.state=not_checked` and
`motion_ready=false`. All verification containers exited. No camera, robot,
leader or simulated motion test was started by this release work.

## Final selectors and rollback

- Local release: `artifacts/releases/ur12e-unified-5185ee5/`;
  `artifacts/releases/current` now points to it.
- PC release: `~/ur12e-unified-5185ee5/`; `~/ur12e-current` now points to it.
- Previous `ur12e-unified-ec64004` release and `ec64004` image remain for rollback.
  Historical images and unrelated training images were not deleted or retagged.
- The unified bundle includes the frozen source/configuration and launch scripts
  required by native teleoperation. The collection CLI/tests use the installed
  image package; native host launchers can resolve the frozen config helpers.
- Isaac Sim 6.0.1 and `~/ur12e-sim` remain external. No Isaac installation, scene
  asset or runtime environment was changed. Its configured native collector
  service can be launched from the new bundle at the next explicit session.
- Existing native commands using `--image ur12e-collection:native-isaac` now select
  the same image as `current`; no separate native image is needed.

Evidence is retained under `artifacts/consolidation-5185ee5/`, including local
and PC test logs, dependency checks, source/image alignment and mount reports.
The checksummed release contains its own manifest, frozen source, dependency
inventory and native launch guide. Deployment documentation is a subsequent
repository update; it does not change the frozen application revision.

