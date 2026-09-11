# M11: Local Encoding and Atomic MCAP Episodes

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Module: M11
- Status: implemented / full-module acceptance pending (encoding/storage slice)
- Parent: [meta plan](../../meta_plan.md)
- Dependencies: M08 accepted frame groups; M10 provenance and state records
- Updated: 2026-09-09
- Alignment: the user approved the proposed M11 encoding/storage increment after M08, with local tests now and lab image deployment next session. The existing meta plan defines H.264, lossless PNG, MCAP + JSON, bounded buffers, and atomic finalization. This document makes that authorized increment concrete; it does not add motion or deployment work.

## Scope and design

Implement reusable Python codecs, a bounded asynchronous episode writer, and independent offline verification. Consume only accepted M08 groups with three 640x480 RGB8/aligned uint16 payloads and an explicit station/calibration/software snapshot. Keep M10 leader intent, issued commands, and actual feedback as distinct records at their supplied rate; never synthesize robot feedback for camera-only fixtures. Include rejection diagnostics and retain original acquisition times and source identities.

Use PyAV 15.1.0/libx264, initial CRF 20, veryfast preset, YUV420P, GOP 30, zero B frames, no lookahead, and repeated Annex B SPS/PPS at keyframes. These are adjustable engineering defaults, not accepted real-scene quality settings. Give every episode fresh encoders. Store acquisition timestamps independently of encoder PTS; relative microsecond encoder times preserve irregular spacing while exact nanoseconds stay in MCAP/metadata. M08 excludes accepted RGB acquisitions less than one microsecond apart using the shared freshness rule; direct codec callers still receive an error for PTS collisions.

Depth uses OpenCV 4.12.0 uint16 PNG compression level 1, preserving zeros and all raw values. Verify every encoded depth frame against its input. Store no raw-image duplicates. Record per-camera depth scale and intrinsics from the supplied snapshot; an uncalibrated snapshot must explicitly say so.

The 2026-09-10 [timing experiments](../m08-frame-matching/timing-diagnosis.md)
evaluate moving immediate PNG decode/equality checks out of the hot path while
retaining mandatory complete-file depth hash verification. This is a proposed
verification-placement change, not weaker losslessness or an already changed
codec default. New tests corrupt a single pixel in a valid PNG for each camera;
all three cases fail final verification and prevent episode completion.

Write a ROS 2-profile MCAP using the official Python `mcap`/`mcap-ros2-support` serializer. This enables native Mac tests without rclpy while retaining ROS 2 CDR schemas: `foxglove_msgs/msg/CompressedVideo` for RGB and `sensor_msgs/msg/CompressedImage` for PNG depth. Versioned provenance/group/control JSON is carried in `std_msgs/msg/String`; records retain `leader/state`, `control/command`, and `follower/state` topics. An explicit snapshot message precedes observations in both file and log-time order. Each log_time is max(acquisition_ns, previous_log_ns + 1), an ordered timeline rather than measured write time. Separate exact RGB/depth acquisition times remain in publish_time and ROS headers; group metadata preserves wrist anchors and signed skews. Images are payload bytes, not file paths. MCAP indexes and CRCs are enabled; chunk recompression is disabled. Direct rosbag2 playback will be checked in the next Jazzy deployment; the offline reader verifies all schemas and message counts now.

One worker owns codecs and the file; a non-blocking bounded submission queue defaults to four groups/events. Full queues or worker errors fail the episode explicitly, never silently drop required data. Ownership transfers on successful submission; callers must not mutate payloads afterward. A caller requests completion, waits with a bounded timeout, and receives the worker result. A timed-out or aborted writer cannot commit later. No storage wait belongs in the future robot control loop.

Create a new `<episode>.partial/` directory exclusively. Stream `episode.mcap`, finish codecs/writer, flush files, independently decode the MCAP, compare stream/group counts and depth digests, then write `metadata.json` and atomically rename within the same parent. Reserve the episode name against concurrent writers and refuse existing destinations. Any encode/write/validation failure leaves a partial directory with explicit failure metadata when writable; it cannot appear as a completed episode. Never resume or overwrite a partial episode automatically.

Record configuration, schema/library versions, codec choices, per-modality payload bytes, file bytes, group/record counts, and timing/queue statistics. Synthetic fixtures are clearly marked; their sizes and timings are not production quality or throughput acceptance. No background SSH, deployment, or scheduled action is introduced.

## Steps and acceptance

1. Add pinned MCAP dependencies and codec/schema helpers.
2. Implement bounded writer ownership, timestamp/group association, and atomic finalization.
3. Add an independent reader/verifier and a CLI validation command; exercise real encode/decode with synthetic images and local saved samples.
4. Update this plan with local results and a reproducible lab verification procedure.

| Case | Criterion | Current result |
| --- | --- | --- |
| M11-A01.1 | Exact uint16 PNG round trips include zero, 65535, and arbitrary per-camera depth scales | PASS locally |
| M11-A02.1 | Independent episodes decode from their own IDR/SPS/PPS; no B frames; irregular acquisition times and group association survive MCAP | PASS locally |
| M11-A03.1 | Bounded queue, encode/write/validation failures, abort/timeout, and existing destinations cannot produce a completed episode | PASS locally; OS filesystem stalls are outside application timing guarantees |
| M11-A04.1 | Independent MCAP reader validates schemas, counts, provenance, depth hashes, and RGB decodability; reports real file/payload sizes | PASS locally |
| M11-A04.2 | Jazzy rosbag2 replay, real-scene quality, and three-camera encoding/storage throughput | NOT RUN; next lab session |

This increment covers the explicitly proposed encoding/storage work. Full LeRobot v3 export/loader acceptance, persistent camera integration, M13 shadow CLI, and 20 real 40-second episodes remain subsequent work. M11 stays acceptance-pending until those applicable full-module requirements are validated.

Sources: [Foxglove video requirements](https://docs.foxglove.dev/docs/sdk/schemas/compressed-video), [official ROS 2 MCAP writer](https://github.com/foxglove/mcap/blob/main/python/mcap-ros2-support/mcap_ros2/writer.py).

## Implementation and validation results

The increment provides `codecs.py`, `archive.py`, `storage.py`, the explicit `episode verify` CLI, and the offline synthetic fixture script. Dependencies pin MCAP 1.4.0 and mcap-ros2-support 0.5.7 in both hashed lockfiles. That pinned ROS 2 writer does not expose the newer `add_metadata` API; the implementation uses an explicit CDR snapshot record instead of depending on an unreleased/private method. No runtime source checkout, ROS graph, SSH, or physical SDK is required by the matching/encoding APIs.

Initial Python 3.12 validation passed 48 tests; three are intentionally skipped (two opt-in Docker mount cases and the Jazzy-only CDR case). Black and Pylint pass with 10.00/10. Tests cover exact depth, RGB fixture PSNR, independent episode decoding, irregular and independent color/depth timing, M08-to-writer integration, preserved raw/missing control data, corruption, metadata mismatch, duplicate groups, empty episodes, concurrent names, queue overflow, explicit abort, completion timeout, and injected codec/disk/verification failures. The timeout test confirms that a worker released after caller timeout cannot later commit.

The final offline fixture is `artifacts/offline/m08-m11-20260909-02/`: 1200 accepted three-camera groups spanning a synthetic 40-second timeline with a deliberate gap. All 3600 RGB frames decode and all 3600 depth hashes verify. The MCAP is 25,575,520 bytes, with observed queue occupancy peaking at one. The measured local generation/encoding/final verification took approximately 17.1 seconds; this producer intentionally waits outside the writer and is not a live real-time test. Full per-modality payload/encoding statistics and linked FFmpeg library versions are recorded in `metadata.json`. The independent CLI verification also passed.

CRF 20 sample checks on one saved RGB image from each actual camera measured approximately 40.45, 41.82 and 41.06 dB RGB PSNR. These are three still-image encode/decode observations, not acceptance of fine task detail, motion quality, GOP bitrate, or a production storage budget. Depth compression in synthetic fixtures is especially favorable; no real-episode capacity claim follows from the 25.6 MB result.

All work in this increment stayed on the Mac; no lab connection or remote deployment was attempted. The [offline validation and deployment guide](offline-validation.md) gives reproducible commands and the next lab steps. Full rosbag2/Foxglove playback, hardware clocks, persistent camera/episode integration, LeRobot v3 export, and the 20 physical episodes remain pending. Filesystem commits assume responsive local storage; application wait limits do not provide a hard real-time bound on kernel filesystem operations.

### Jazzy container verification

The initial local arm64 development image was `ur12e-collection:m08-m11-dev`, ID `sha256:6482798f301a4ec82dbb153c0916b82bfded1ad74351ba6f5c65bd06b454ab89`, labeled `48ad1f7-working-m08-m11`. With `--network none` and no devices, its final test run passed 49 tests and skipped only the two opt-in Docker mount cases. `M11-A04.3` PASS: actual `rclpy.serialization` deserializes the stored standard depth and String CDR messages with preserved depth pixels and acquisition timestamps. This does not establish full video playback in rosbag2/Foxglove.

The earlier v3 amd64 foundation bundle predates M08/M11 and must not be presented as containing this increment. No updated amd64 production image or release archive was built during this offline session.

## Aligned review corrections (2026-09-09)

Implement the cross-module corrections in the
[M08 review plan](../m08-frame-matching/plan.md#aligned-review-corrections-2026-09-09).
Share MatchConfig and accepted-frame freshness with M08, preserving fatal checks
for violated writer contracts. Record the matching configuration alongside the
snapshot without redesigning the snapshot. Validate every group's image inputs
before advancing any encoder. Separate exact acquisition publish_time from a
strictly increasing ordered log_time; declare this convention in episode context
and verify it on read. Test both MCAP iteration orders with real signed skew and
late non-image records. Snapshot schema/builder and throughput architecture are
outside this correction increment. Results will be recorded after execution.

### Correction results

PASS on 2026-09-09: M11-A02.1/A03.1/A04.1 cover the shared matching contract,
non-default skew persisted and independently verified, bad-depth rejection with
successful subsequent groups, and image preflight before any encoder advances.
Signed camera skews (-12 ms and +12 ms), separate depth times, late control and
rejection records, and control-first recording preserve all acquisition times.
File-order and log-time-order reads produce identical ordered records with
snapshot/group context preceding payloads. The verifier checks the declared
ordered-log convention and rejects metadata/configuration disagreement.

Validation commands and actual results:

- `PATH="$PWD/.venv/bin:$PATH" PYLINTHOME=/private/tmp/ur12e-pylint ./scripts/check`:
  PASS, Black unchanged, Pylint 10.00/10, 66 tests passed and three skipped.
- Local arm64 Jazzy test run with `--network none`: PASS, 67 passed and two
  skipped (opt-in host Docker cases); includes M11-A04.3 standard ROS CDR decoding.
- Host opt-in `tests/test_containers.py` against the new image: PASS, both
  replacement persistence and read-only mount checks. No Docker-in-Docker use.
- Fresh 1200-group fixture and independent `ur-collect episode verify`: PASS,
  all 3600 RGB frames decoded and 3600 depth hashes verified; 25,575,642 MCAP
  bytes. Evidence: `artifacts/offline/m08-m11-review-20260909/`. This is a
  synthetic, producer-paced codec/recording regression, not a throughput result.

Image: `ur12e-collection:m08-m11-review`, arm64,
`sha256:734afd14434400c01baee4f3d8a0a58bd13ef0fd84f17a00f8c5146ed3945ce8`,
source label `48ad1f7-working-review-2-4`. This image contains the reviewed code
and tests; documentation-only acceptance updates followed its build. The first
sandboxed build failed to write Docker Buildx's activity file; the authorized
retry completed normally. No sudo, remote connection or deployment was used.

M11-A04.2 remains NOT RUN: actual rosbag2/Foxglove playback, real-scene quality,
and combined camera/matching/encoding/control throughput need lab validation.
Snapshot schema/builder, encoding concurrency, M09 integration, M13 shadow, and
LeRobot export remain deferred. Earlier uncommitted fixture archives predate the
explicit recording time/configuration contract and remain historical artifacts.


The M13 increment replaces the handwritten snapshot validator with M10's shared
versioned schema/builder. Final Jazzy tests cover standard video CDR and native
rosbag2 MCAP reading; CLI info/play smoke also passed without a GUI subscriber.
Camera-only repeated episodes now exercise the recorder with persistent sources.
See [M13 results](../m13-acceptance/plan.md) for evidence, image identity and the
emulated-runtime overflow. Real-scene quality/throughput and LeRobot export
remain pending; full M11 acceptance is not claimed.


The 2026-09-10 [software baseline](../m13-acceptance/software-baseline.md) closes
the tested software slice of this module. Remaining hardware or unimplemented
full-module cases stay open; repeat software checks only for affected changes
or new failures.

## Read-only integration increment

Mandatory final-file depth hashes replace inline PNG decode checks. A reproduced runtime queue failure led to independent bounded admission for four ordinary group/event items and 64 feedback records, with one ordered FIFO and writer. Both overflow paths fail explicitly. Corrupted feedback identity is rejected by independent file verification; pixel-corruption regression coverage remains in place. See the
[shared plan and results](../m13-acceptance/readonly-integration.md).


The 2026-09-10 [simulation-session increment](../m09-session/plan.md#autonomous-simulation-session-increment-2026-09-10)
adds a process boundary around recording and a recoverable outcome marker.
Verified MCAP and snapshot contents remain immutable across discard/review.


Controlled simulator recording now prepares the writer before following starts,
requires measured stop before commit, and verifies MCAP in a separate persistent
process. Bounded slot/queue failure aborts the episode. Short and two 40-second
URSim sessions plus fault/restart cases pass; full 20 x 40 remains pending.
The explicit optional [LeRobot projection](lerobot-export.md) passes real official
writer/loader validation; it does not replace authoritative RGB-D MCAP storage.

## Simulator queue-budget audit

The shared-memory 20 x 40-second batch completed 14 episodes and then failed
with a generic writer overflow (`session-1789027660592731838`). Source counters
showed no lost native frames; source delivery peaked at 126 ms. Completed episodes
spent approximately 15–16 ms per camera triple encoding, below the 33.3 ms input
period. This does not establish the exact failing queue, because the previous
error did not include its category or occupancy.

Add explicit category/occupancy/capacity and writer operation timing to failure
reports. Match the simulator's lightweight record budget to its bounded 500 ms
recorder supervision interval: four control records per 50 Hz tick need 100
slots before supervision expires; reserve 128 in the simulator profile. The
existing 64-record physical/shadow default remains unchanged. The 16-triple image
budget already represents approximately 533 ms. Queues still fail closed, actual
control freshness/watchdog and camera matching remain unchanged, and queued
records cannot drive new motion. Validate independent record/image capacity and
a deliberately stalled writer, then rerun the full batch. Do not describe this
budget correction alone as proof of the previous failure's root cause.

The budget/diagnostic increment passes 69 targeted storage/feedback/session tests,
then the full Mac suite (232 PASS / 4 skipped) with Black/Pylint 10.00/10.
A deliberately blocked writer accepts the configured 128 small records without
consuming image slots and rejects the next record with exact occupancy evidence.
The new frozen 20-episode batch is running; its acceptance remains pending.


The corrected simulator batch `session-1789028767567594961` completes all twenty
40-second episodes and passes the independent current audit. The observed record
queue peak is 68/128, image peak 10/16, maximum queue delay 339.03 ms. Each MCAP
is independently decoded and all depth hashes verified. This closes the simulator
long-duration gate; it does not change physical resource/quality acceptance.

### N4/N6 recorded-image workload increment

The aligned offline sprint resumes resource debugging with real recorded inputs.
The first amd64 Docker run failed after 20 encoded groups: average group work
59.5 ms, exceeding the 33.3 ms input period; the bounded 16-group queue correctly
aborted. Camera producer queues peaked at one. Preserve the failed evidence.

Add an explicit `encoding_workers=3` snapshot option for the simulator workload.
Exactly one RGB/depth job per camera can run concurrently; all three finish before
the single MCAP owner serializes the group or starts another. Codec contexts are
never used concurrently with themselves. Preserve H.264 CRF20/veryfast, PNG level1,
depth hashes, FIFO order and all queue/freshness gates. Serial remains the default
for previously accepted physical profiles. Reap workers after success or failure.
Performance and final-image acceptance remain NOT RUN for this increment.


### Offline replay resource follow-up (2026-09-11)

The actual URSim plus recorded RGB-D 40-second file independently verifies all
RGB/depth payloads and uses 460.0 MB for 1,196 groups. Three concurrent camera
codec jobs retain byte-identical outputs in regression, while one MCAP writer
keeps archive order. Both simulation input variants use this explicit three-job
profile; physical/shadow encoding defaults are unchanged. Repeated Mac amd64
full-load quality remains FAIL. See M13 `offline-completion.md` for gate values,
exact failure records and extrapolated storage cost; a short success is not a
sustained-throughput acceptance.
