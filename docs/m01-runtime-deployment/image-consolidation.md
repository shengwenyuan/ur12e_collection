# M01: One Current Collector Image

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned maintenance scope / implementing, 2026-09-11.

The user requested consolidation of current images and an explicit removal list
after verification. Use one current collector image for daily collection,
simulator clients and development tests. Preserve existing images until the user
reviews the concrete cleanup list. No lab access, device operations or motion
are needed for image consolidation. The application/control code is unchanged.

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
