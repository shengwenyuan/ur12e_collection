# Offline Validation and Next Lab Deployment

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

## Current scope

M08 matching and the M11 encoding/storage API run without SSH, physical cameras, or robot motion. Session/shadow/calibration commands remain unavailable. The fixture script is explicitly synthetic and cannot claim accepted physical demonstrations. The user requested local checks now and lab deployment during the next lab session; no remote connection or scheduled deployment was made.

## Local checks

Use the provisioned Python 3.12 environment:

```sh
uv pip install --require-hashes -r requirements/development.txt
uv pip install --no-deps -e .
source .venv/bin/activate
./scripts/check
python scripts/write_fixture_episode.py artifacts/offline/new-fixture --frames 1200
ur-collect episode verify artifacts/offline/new-fixture
```

Every output directory must be new. The fixture contains three synthetic 480p RGB-D views, explicit synthetic identities, no robot feedback, a deliberate acquisition gap, and distinct RGB/depth timestamps. Its producer may wait outside the recorder; `EpisodeWriter.submit()` itself never blocks. A 1200-group run exercises independent H.264 keyframes and full MCAP decode, not real-time sensor throughput or a storage budget for real scenes.

Historical M07 logs can exercise the actual matcher:

```sh
python scripts/replay_camera_timestamps.py \
  --wrist /path/to/wrist.jsonl \
  --third-left /path/to/analysis-view-a.jsonl \
  --third-right /path/to/analysis-view-b.jsonl \
  --assume-common-clock
```

This deliberately assumes SDK global-time comparability. Role arguments are analysis labels, not station identity registration. Clock calibration, bounded wait effects, camera startup convergence, and actual left/right bindings still need lab validation. The script rejects raw independent hardware clocks.

For a native Mac Docker check, build a separate arm64 development image. Tests run with no network or device mapping:

```sh
docker build --target development -t ur12e-collection:m08-m11-dev .
docker run --rm --network none --entrypoint /bin/bash \
  ur12e-collection:m08-m11-dev -c \
  'source /opt/ros/jazzy/setup.bash && cd /opt && python -m pytest -q -o cache_dir=/tmp/pytest-cache tests'
```

The Jazzy-only test uses `rclpy.serialization` to deserialize actual standard ROS 2 CDR depth and metadata messages. Foxglove video CDR is independently decoded by the official MCAP dynamic reader; full rosbag2/Foxglove playback remains a separate deployment check.

## Library interfaces

`matching.Frame` requires role, generation, an explicitly established common-clock ID, separate mapped color/depth nanoseconds, original color/depth `Provenance`, and an optional payload. `Matcher.push(frame, now_ns)`, `advance(now_ns)`, and `finish(now_ns)` return accepted triples or explicit rejected anchors. `push` always raises `matching.SourceFault` on a source discontinuity, including when no wrist is pending. The exception carries `generation` and a bounded tuple of pending-anchor `rejections`; handle the fault even when that tuple is empty. M07 owns generation allocation/readiness, M09 owns episode termination and M06 stop/hold requests. Use `reset(new_generation)` only after explicit recovery; reconnecting never resumes following automatically. These live owners remain unimplemented.

For recording, attach owned `codecs.Images(rgb, depth)` arrays to frames. Pass a snapshot containing task, software revision, `clock_epoch="unix"`, clock ID, calibration or explicit null, and each camera's unique source identity, positive depth scale, and 640x480 color intrinsics. Pass the same `MatchConfig` to `Matcher` and `storage.EpisodeWriter(destination, snapshot, simulated=..., match_config=config)`; successful `submit(match)` transfers ownership, and arrays must not be mutated afterward. Rejections become diagnostics without images. `submit_record(record, mapped_unix_ns)` retains the separate `leader/state`, `control/command`, and `follower/state` semantics. The caller owns source-clock mapping; the writer does not infer it.

Monitor `health()` for asynchronous failures. `finish(timeout=...)` is a finalization operation outside the control loop; it flushes, verifies, and commits. `abort()` prevents subsequent commitment before the commit gate. Queue and verification waiting is bounded; no Python deadline can guarantee latency while the operating system stalls an atomic rename or filesystem sync. Data mounts must be local, and robot-side host-stall protection remains M03/M06 work. Do not run finalization in a servo callback.

An episode name is reserved against cooperating writers. Existing complete/partial destinations are never automatically overwritten or resumed. Failures retain `<name>.partial/` and, when writable, `failure.json`. Only a successfully verified directory is renamed to the complete destination. Inspect partial files explicitly; do not bulk-delete them during startup.

## Next lab session

These are planned actions, not completed deployment results:

1. Synchronize the reviewed repository revision when `ur12e-collection` is reachable. Preserve existing station configuration, recordings, and prior image archives.
2. Build amd64 development/runtime images on the Ubuntu collection PC using the pinned Dockerfile and hashed requirements. Record the actual source revision in `SOURCE_REVISION`. Do not deploy the Mac arm64 development image as an amd64 release.
3. Run the software suite with ROS Jazzy plugins, then `scripts/run station doctor --backend hardware --format json --require-mounts`.
4. Verify an offline fixture through the installed runtime and inspect ROS 2/Foxglove video replay. Build the delivery bundle with `scripts/release.py` only from the validated amd64 runtime.
5. Resolve actual camera roles and clock mapping before connecting M08/M11 to a persistent camera source. Run three-camera shadow encoding once that M13 integration exists. The previous 40-second camera diagnostic did not encode every frame.
6. The confirmed UR12e controller address is `10.18.1.106`; keep actual UR feedback, Hand-E protocol, GELLO hardware, ZERO/READY routes, and motion acceptance separate. This deployment does not authorize movement.

LeRobot v3 export and the complete 20-episode hardware acceptance remain pending. Do not mark all of M11 accepted from these software checks.

## Corrected recording contract

Accepted RGB members must advance by at least 1000 ns and depth times must
increase, alongside strictly new color/depth counters. Invalid candidates are
rejected by M08 before encoding; M11 still fails on a forged accepted group.
The matching configuration is stored in the episode context and checked against
metadata.json during verification. Snapshot schema/builder work remains deferred.

All MCAP log_time values strictly increase in file order using
max(acquisition_ns, previous_log_ns + 1). This ordering coordinate can differ from
acquisition time for skewed views and late control records. Consumers must use
publish_time, image headers and provenance for synchronization or training.
The `ordered_log_acquisition_publish_v1` marker declares the convention. Earlier
uncommitted fixture archives lack this contract and are historical evidence;
regenerate a fixture for validation of this revision rather than rewriting it.
