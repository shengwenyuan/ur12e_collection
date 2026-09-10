# M07/M08/M11/M13: Resource Allocation and Camera Gates

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: candidate passed the physical batch; the user approved productionizing the profile. See the current read-only integration results for released-code and deployment boundaries.
The user approved timing/concurrency experiments on 2026-09-10. This document
defines the proposed production settings; it does not silently change defaults
or declare untested robot control accepted.

## Ownership and resources

Use three persistent acquisition processes, one per camera. Each owns its SDK
pipeline, alignment and bounded output queue. The parent alone owns matching
and nonblocking writer submission. Keep a single writer thread owning the three
independent H.264 contexts and ordered MCAP output. The finalizer waits for flush
and complete-file validation while acquisition continues. No additional encoder
pool, GPU, shared-memory transport, CPU affinity or real-time scheduling is
required by the current candidate.

Use `--memory 4g --memory-swap 4g` without a hard CPU quota for the next candidate.
The initial four-core quota passed two short runs but failed an interference
case: an additional in-container Python/OpenCV environment probe coincided with
CPU throttling, three D435IF frame gaps, 88 ms delivery latency and 109 ms writer
queue delay. Docker exec events place that probe approximately 0.16 seconds before
the first observed gap. This is not proof that isolated capture needs more than
four cores. The candidate avoids hard throttling to preserve burst headroom;
it does not claim a proven minimum CPU requirement.
The memory limit includes reclaimable page cache, and swap is disabled for the
container. Robot control must retain separate ownership and must never wait on
camera matching or disk work. Combined robot/control load is not yet measured.

The two no-quota candidate episodes used approximately 1.15 CPU core equivalents
on average (one-second sample p95 1.40, startup sample maximum 3.98). Group handling
averaged 22.08 ms with p95 23.13 ms. Provision CPU burst headroom rather than
turning the average into a hard bandwidth quota. Any future CPU pinning or shared
robot-control deployment requires a separate interference test.

One 640x480 RGB8 plus uint16 depth frame pair is 1,536,000 raw bytes. Four queued
pairs per camera allow approximately 18.4 MB across acquisition queues; eight
references per camera allow at most approximately 36.9 MB of referenced image
data in matching; four queued three-view groups allow approximately 18.4 MB at
the writer. These are logical payload bounds, not an RSS limit: copies, feeder
buffers, codecs, verification and the OS page cache require additional memory.

Short runs stored approximately 325-327 MB per 40-second episode; the final batch
stored 390-420 MB per episode, or approximately 36.7 GB per recorded hour
(excluding inter-episode time). PNG depth
dominates storage. This is an empirical capacity estimate, not a fixed bitrate;
RGB texture, motion and depth noise can change it. Keep the report's actual
per-topic payload bytes and final MCAP size when sizing collection storage.

## Proposed runtime settings

| Setting | Candidate | Scope |
| --- | --- | --- |
| RGB/depth profile | 640x480, 30 Hz, RGB8 / raw Z16 | Preserve source identity, timestamps, depth scale and aligned pixels |
| Timestamp skew | Inclusive 16.7 ms | Never substitute host receipt for acquisition time |
| Matcher wait | 75 ms from wrist SDK receipt | Earlier decision when both streams advance through the anchor; this is not an added robot-control delay |
| Empty supervisor wait | 1 ms | Existing polling design, with bounded sleeping rather than a busy spin |
| Capture-tail drain | Same 75 ms budget after the logical cutoff | Admit only pre-cutoff SDK receipts; in-boundary arrivals during finalization fail explicitly; the recorded sample interval remains 40 seconds |
| Matching buffer | 8 references per role | No unbounded accumulation |
| Acquisition / writer queues | 4 pairs per role / 4 groups | Overflow is explicit failure |
| RGB codec | H.264 CRF 20, veryfast, yuv420p, GOP 30, no B frames, one encoder thread per context | Unchanged image-quality contract |
| Depth codec | uint16 PNG level 1 | Encode once; verify every stored depth hash in mandatory final-file validation |
| Completion | Full RGB decode plus all depth hashes before atomic completion | Any failure retains a partial and prevents success |
| Lifecycle limits | 2-second alignment warm-up; 30-second startup; 2-second stale timeout; 30-second finalization timeout | Existing bounds; not motion safety deadlines |
| Source integrity | No backward/repeated RGB identity or timestamp; track depth repeats/gaps separately | Never manufacture or reuse a frame to satisfy an output-rate target |

The experiment moves immediate PNG decode/equality checking out of the encoding
hot path, but retains codec unit tests and the final independent file check.
Production implementation must preserve input shape/dtype validation and test
corruption detection before enabling this change. The experiment's simplified
wrapper is not a released codec API.

## Proposed acceptance gates

These numerical thresholds are proposals to review with the user, not previously
agreed pass criteria. A completed file and a passed collection gate are different
results. A gate failure must remain visible even when its partial or complete
file is retained for diagnosis.

1. **M13-A03 batch:** 20 completed 40-second episodes in one persistent rig run,
   no failed/interrupted episode counted toward the 20; all independent file
   checks pass.
2. **M07 source stability:** zero source color/depth counter gaps and zero repeated
   source frames in the untouched steady run; no worker exit, stale stream,
   unexpected USB reconnect or queue overflow. Operator-induced disconnect is a
   separate fault-injection result, never folded into normal-run statistics.
3. **M08 grouping:** account for every in-boundary wrist anchor; accept at least
   99.5% per episode and 99.7% over the batch. Include start/end boundary rejections
   in the denominator. Accepted identities are unique and every view satisfies
   16.7 ms. Every rejection retains its reason; investigate any consecutive run
   above two rejected anchors. Do not require an artificial 1200 groups.
4. **M11 headroom:** group processing p95 below 30 ms under real inputs; writer
   queue peak at most 3 of 4 and no overflow. Report per-stream codec time, parent
   delivery and decision-latency percentiles, disk bytes, finalization duration,
   CPU and memory. These performance gates need production instrumentation;
   current experimental measurements alone do not add a runtime enforcement path.
5. **M13-A04 boundaries:** physical left/right binding, physical clock accuracy,
   visual quality and robot/control integration remain independently identified.
   Camera throughput results do not close those cases.

## Experiment evidence

See [timing diagnosis](timing-diagnosis.md) and
[physical connection comparison](../m13-acceptance/physical-20260910.md).
The base runtime is the immutable image recorded there, corresponding to commit
`4f046a9`. Disposable instrumentation and wrappers live under ignored
`artifacts/experiments/timing-20260910/` locally and the deployed bundle's
`evidence/timing-20260910/` on the station. Each run records its settings and
preserves the actual wait in episode metadata. Production station configuration,
image and timing/codec defaults remain unchanged while final settings are reviewed.
The separately implemented M09/M13 tail-drain correction is tested using explicit
read-only source overlays; its source hashes accompany experimental evidence.

## Final candidate results (2026-09-10)

Run `timing-20260910-batch20-drain-01` completed successfully with exit code zero.
All proposed gates above passed in this run; adopting them as production policy
still requires the requested user alignment.

| Measurement | Result |
| --- | --- |
| Duration / ownership | 20 episodes, exactly 40.000 seconds each, one persistent rig |
| Anchor accounting | All 23,995 in-boundary wrist receipts match decisions one-to-one; zero unaccounted anchors |
| Grouping | 23,945 accepted, 99.7916% overall; worst episode 99.6664%; 30 reuse and 20 skew rejections; maximum rejection streak one |
| Source stability | 30,326 wrist / 30,311 left-slot / 30,312 right-slot frames including finalization, zero color/depth gaps or repeats |
| File integrity | All 20 files independently verified; every recorded RGB frame decoded and all 71,835 depth hashes verified |
| Group processing | Mean 19.91 ms, p95 22.15 ms, maximum 39.41 ms |
| Queue | Peak one of four; maximum delay 13.47 ms; no overflow |
| Delivery | Per-role p95 5.49-6.29 ms; maximum supervisor-observed delivery below 20 ms |
| CPU | Mean 1.08 core equivalents, one-second p95 1.39; startup sample maximum 4.36; no CPU throttling |
| Memory | Sampled anonymous-memory peak 1.11 GiB; cgroup peak 4 GiB including reclaimable file cache; no OOM or OOM kill |
| Final verification | Mean 10.43 seconds, maximum 10.74 seconds per episode; acquisition continues |
| Storage | 8,145,691,859 MCAP bytes; 7.81 GB depth payload and 0.25 GB RGB payload |

Source/payload diagnostics were active during these measurements. No extra
encoder workers or GPU were added. All containers exited, the production station
checksum is unchanged, and no robot motion occurred. Physical role binding,
exposure-clock accuracy, scene-quality review and combined robot load remain
separate acceptance work. Production timing/codec defaults are not yet changed.

The reproducible experimental command is the fixed `run-drain-v1.sh` launcher
with arguments `batch20-drain-01 75 1 final 20 memory drain`; the base image and
overlay/probe/runner hashes are in `drain-manifest.json`. The local
`batch20-drain-01/batch-summary.json` checks receipt identity accounting as well
as counts; reports, original source traces and failure evidence remain retained.

The [read-only increment](../m13-acceptance/readonly-integration.md) promotes
the runtime profile and introduces a separately bounded 64-record feedback
admission budget. The original image/group queue stays at four; new-image
physical integration is pending. Earlier experimental measurements below remain
historical evidence, not claims about a newly deployed image.
