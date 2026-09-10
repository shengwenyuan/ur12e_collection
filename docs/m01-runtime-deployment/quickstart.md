# UR12e Collection Foundation Quickstart

This runtime provides software diagnostics, station configuration, camera-only or output-only observation shadow, verified MCAP recording and offline calibration. Explicit isolated URSim sessions support native HOME and teleoperation tests. Physical control remains disabled; there is one READY/HOME target and no separate ZERO movement. See the capability matrix and M13 lab runbook for acceptance boundaries.

The user-confirmed UR12e controller IP is `10.18.1.106` (2026-09-10).
The collection PC remains `ssh ur12e-collection`. These are separate devices;
recording-camera commands do not initialize either robot or gripper control.

## Source development

Use Python 3.12. Install `requirements/development.txt` with hash verification into a virtual environment, then install this package with `pip install --no-deps -e .`. Run `pytest`, `black --check src tests scripts/release.py`, and `pylint src/ur12e_collection` with this repository's configuration. The Mac does not need lab SSH access. Hardware SDK availability differs between arm64 development and amd64 production.

```sh
docker build --platform linux/amd64 --target development -t ur12e-collection:current .
./scripts/run dev doctor --format json --require-mounts
```

The development profile has no network or device access. Its host configuration/data folders are `config/local/` and `data/`, both ignored by Git. Rebuilding is explicit; the launcher never pulls or builds an image automatically.

## Ubuntu station

Prerequisites: Ubuntu 24.04 amd64, Docker Engine and Compose available to the operator, and Python 3.12. The verified lab machine uses Docker 29.4.0 / Compose 5.1.2. Administrator setup creates writable `/var/lib/ur12e-collection` and `/var/lib/ur12e-collection/data`; do not make the Docker socket world-writable.

From a source checkout, build the runtime image. From an offline bundle, run its loader instead; a source checkout and registry access are unnecessary:

```sh
./scripts/load-release
./scripts/run station doctor --backend hardware --format json --require-mounts
./scripts/run station station initialize --output /config/station.json
./scripts/run station station validate /config/station.json
```

Initialization creates an incomplete draft and refuses to overwrite an existing station file. Fill observed identities before camera-ready validation. `motion_accepted` remains false; this configuration revision cannot authorize real motion. The `station` profile uses Linux host networking but grants no USB devices by default. On Ubuntu, `./scripts/camera-probe` explicitly maps the USB bus and RealSense video nodes, running as the operator UID/GID. Existing host udev permissions must allow that user to open devices. Close RealSense Viewer before capture; only one owner may open each camera.

```sh
./scripts/camera-probe
./scripts/camera-probe --seconds 10 --output /data/probes/new-check
```

This probe preserves source clocks and does not claim cross-camera synchronization. It is separate from the persistent `shadow` command. Unknown left/right camera assignments remain unbound. The current source uses one spawned worker per camera and warms alignment before measuring. Review color gaps and repeated/missing depth counters separately; a completed probe is not a guarantee of 30 unique depth frames per second. Only one RGB/depth sample pair is saved per camera, alongside per-frame timestamps; this is not a full video recording.

Override `UR12E_CONFIG_DIR` and `UR12E_DATA_DIR` with existing writable absolute host directories when needed. The launcher uses the operator UID/GID; explicit `UR12E_UID`/`UR12E_GID` overrides are available for a deliberately configured deployment account. Container replacement preserves these mounts.

## Release creation

```sh
python3 scripts/release.py ur12e-collection:current /path/to/new-bundle
```

The bundle contains the image, exact image identity, package manifests, checksums, launcher, Compose file, example configuration, and this guide. Bundle creation leaves a `.partial` directory on failure and never overwrites an existing destination. The loader checks file integrity before loading; the bundled launcher selects the recorded image ID. These checks establish integrity, not a signature or publisher-authentication scheme.

Keep credentials and real station data outside the bundle. Hardware acceptance and real three-camera throughput remain separate from successful image loading and software diagnostics.

The daily image is `ur12e-collection:current` for collection, development and
simulator clients. It includes the runtime plus test tools. Use `UR12E_IMAGE`
to override it explicitly; the old `UR12E_DEV_IMAGE` split is retired. Bundle
manifests pin an immutable image ID for both profiles. The bundle includes
`CALIBRATION.md` and `CAPABILITIES.md`. Calibration solve/verify/setup/activate
are offline commands and send no motion. Optional LeRobot export requires its
separately documented dependency environment; Torch/LeRobot are not bundled.
The runtime image contains simulator adapters, but this Ubuntu delivery does not
include the official URSim appliance or authorize physical control. Use the
repository simulator launcher and setup instructions for local URSim testing.


The [image consolidation record](image-consolidation.md) identifies the current
image, verification results and explicit old-image cleanup candidates. Local
`artifacts/releases/current` points to the verified current bundle; old bundles
remain immutable until separately reviewed for removal. Official URSim stays a
separate appliance image. One collector image does not mean combining its
controller process or persistent volumes into the collection container.
