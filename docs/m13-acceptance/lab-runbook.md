# Camera Batch: Lab Deployment and Acceptance

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

## Scope and prerequisites

The [software baseline](software-baseline.md) is accepted. This visit targets the
remaining physical evidence; do not repeat the full offline suite or image build
without a relevant change or failure. Keep the real-file verifier enabled as an
integrity check of newly acquired data.

Target: Ubuntu 24.04 amd64, ROS 2 Jazzy, Python 3.12, librealsense Python
2.56.5.9235, PyAV 15.1.0, OpenCV 4.12.0.88, MCAP 1.4.0 and ROS 2 support 0.5.7.
Use the pinned Dockerfile/base digest and hashed requirements. Deployment host
alias: `ur12e-collection`; it is reachable only when the lab network is available.
The user-confirmed UR12e controller IP is `10.18.1.106`; do not infer it from the collection-PC SSH alias. Camera-only commands do not connect to that address.

This batch starts cameras only. It neither connects to UR/GELLO/Hand-E nor moves
joints. Move scene objects by hand for RGB motion/detail assessment. Physical
leading, Space/READY/hold and calibration tests are separate, pending modules.

Robot follow-up reference: the [actual unit inventory](../m03-ur-adapter/controller-inventory.md)
records user-reported UR Software `5.22.1`, identity, component versions and
installed URCaps, including `External Control` and `Robotiq_Grippers`. For a
separate read-only robot inspection, reconcile DHCP and the pendant message
`Not connected to network!` with reported ping reachability; confirm the current
address and controller identity before checking Dashboard, RTDE or the candidate
Hand-E service. Package presence and ping do not establish service readiness.
These checks are outside this camera-only batch and remain pending.

## Deploy a prepared bundle

Copy the complete amd64 bundle to the lab PC, then from its directory:

```sh
./scripts/load-release
export UR12E_CONFIG_DIR=/var/lib/ur12e-collection
export UR12E_DATA_DIR=/var/lib/ur12e-collection/data
./scripts/run station doctor --backend hardware --format json --require-mounts
./scripts/camera-probe
```

The loader verifies checksums. Bundle launchers select its immutable image ID.
Keep existing configuration, recordings and image archives. Never use a Mac
arm64 image as the amd64 release. The configured operator must have writable
local data mounts and access to the RealSense USB/video nodes; the launcher uses
the operator UID/GID and explicit device mappings, without privileged mode.

Alternatively build from the reviewed source checkout on the Ubuntu PC:

```sh
revision=$(git rev-parse HEAD)
docker build --platform linux/amd64 --target development \
  --build-arg SOURCE_REVISION="$revision" -t ur12e-collection:shadow-dev .
docker run --rm --network none --entrypoint /bin/bash \
  ur12e-collection:shadow-dev -c \
  'source /opt/ros/jazzy/setup.bash && cd /opt && python -m pytest -q -o cache_dir=/tmp/pytest tests'
docker build --platform linux/amd64 --target runtime \
  --build-arg SOURCE_REVISION="$revision" -t ur12e-collection:shadow-runtime .
export UR12E_IMAGE=ur12e-collection:shadow-runtime
```

## Bind the actual camera roles

Set `station_id` and the three model/serial pairs in the local station.json.
Use the observed D405 for wrist; physically identify left and right D435IF units.
Do not derive roles from discovery order. Preserve unknown UR/Hand-E/READY fields
as null, GELLO unavailable, motion_accepted false, and calibration null.

```sh
./scripts/run station station validate /config/station.json --cameras-ready
```

Close RealSense Viewer before capture. Keep the current two-hub topology for the
first comparison; inventory records USB speed and firmware. Stop on identity,
profile or permission errors instead of changing station identities to bypass them.

## Smoke, then the full batch

Use new output names. For a release bundle, obtain its recorded revision:

```sh
revision=$(python3 -c 'import json; print(json.load(open("manifest.json"))["source_revision"])')
./scripts/camera-shadow --station /config/station.json \
  --revision "$revision" --output /data/shadow-smoke \
  --episodes 2 --seconds 2
./scripts/camera-shadow --station /config/station.json \
  --revision "$revision" --output /data/shadow-20x40 \
  --episodes 20 --seconds 40
```

For a source checkout use its actual tested revision instead of manifest.json.
The camera workers stay alive across every episode and finalization interval.
Default writer queue capacity is four events; each camera queue holds four frames.
No producer-side pacing waits for encoding capacity in hardware or synthetic
shadow. Overflow fails explicitly. Failed/interrupted work remains partial;
completed earlier episodes remain available. Ctrl+C aborts active work and closes
all camera workers, never starting a READY action.

The batch `report.json` records requested/completed episodes, exact receipt
boundaries, matching counts, per-role acquisition counts/gaps/repeats/delivery
latency, codec/queue costs, bytes per modality and source context. Supervisor peak
RSS excludes camera workers; observe full container CPU/memory separately with
`docker stats`. This report is a measurement record, not an automatic declaration
that physical clock accuracy or RGB quality passed.

## Acceptance checklist

- M07: roles and models agree; three persistent 640x480 RGB8/aligned Z16 streams
  at configured 30 Hz; inspect actual rates, gaps/repeats and maximum delays.
- M08: only actual frames within 16.7 ms enter groups, with separate original
  RGB/depth times; inspect rejected-group reasons and rate. No filler frames.
- M10: snapshot schema/version, station, intrinsics/depth scale and revision
  agree. Calibration remains explicitly null for this batch.
- M11/M13: 20 completed directories, each independently decodable; inspect depth
  verification, compression costs and queue headroom. Run `episode verify` again
  on selected completed episodes, then inspect `ros2 bag info` / actual playback
  and RGB detail. The runtime image must provide the required rosbag2 MCAP plugin;
  missing tools are a failed deployment prerequisite, not a playback pass.
- SDK global-time domains are required and sanity checked against host time.
  Hardware clock accuracy remains unvalidated; do not equate successful software
  matching with simultaneous exposure. Record clock findings before acceptance.
- Exercise Ctrl+C and a deliberate camera disconnect in separate new short runs.
  Neither may create a falsely completed episode or leave a camera worker alive.
  Re-run with a new directory after resolving the fault; no automatic resume.

No unagreed rejection-rate, RGB-quality or storage-cost threshold is invented.
Record the measured values and align any tolerance needed to accept the batch.
If 20 x 40 seconds fails, retain its report/partials and diagnose the earliest
cause before increasing queues or changing codecs.

## Prepared local candidate

The final local bundle is `artifacts/releases/ur12e-shadow-bundle-20260910/`.
Its runtime image is amd64 and its source label explicitly identifies a working
increment (`15c9d26-working-shadow`). Use the manifest/image checksum as the
artifact identity; this label is not a claim of a new clean Git commit.
The [M13 plan](plan.md) records software tests, exact versions, the concurrent
emulation overflow and isolated rerun, and remaining physical acceptance.
