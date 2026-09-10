# M08: Live Timing Diagnosis and Proposed Correction

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: experiments complete / candidate gates passed; production settings awaiting alignment.
On 2026-09-10 the user required resolving grouping losses and requested a timing
breakdown before choosing additional concurrency or other changes. The current
50 ms wait and 16.7 ms skew contracts remain unchanged as the baseline.
The user subsequently approved the proposed diagnostic and correction experiments,
requesting measured resource allocation and final gate settings for alignment.
Run camera-only experiments with explicit configurations and isolated evidence;
keep the production station unchanged. Final recommended thresholds remain a
proposal until reviewed with the user.

## Measured baseline

Use the unchanged `4f046a9` runtime and the direct D405 connection documented in
[physical acceptance](../m13-acceptance/physical-20260910.md). Two 40-second
recordings accepted 987/1200 and 1117/1199 decided wrist anchors (82.25% and
93.16%). Every source had zero counter gaps/repeats, and both files verified.
This is not complete grouped-stream acceptance.

| Stage | Measurement or configured bound | Meaning |
| --- | --- | --- |
| Source period | Approximately 33.33 ms | Frame production interval, not CPU time |
| Nearest third-view receipt relative to wrist | Left median 20.76 ms, maximum 30.47 ms; right median 31.19 ms, maximum 40.60 ms | Measured from the separate 40-second source-only trace, excluding two wrist frames at each boundary; acquisition phase and delivery timing, not compute time |
| SDK frameset receipt to supervisor observation | Recording maxima: wrist 17.46 ms, left 17.82 ms, right 23.12 ms | Combined alignment, copies, process transport and supervisor scheduling; individual stages are not yet timed |
| Empty supervisor poll | Up to 10 ms requested sleep | Configured behavior, not measured scheduling latency; already included in the observation bound above |
| Matcher wait | 50 ms from wrist SDK receipt | Includes upstream image preparation/transport time; separate from the 16.7 ms acquisition timestamp skew limit |
| Accepted decision latency | Medians 52.52 / 49.81 ms; p95 59.26 / 58.39 ms | Receipt-to-decision wall time, not matcher CPU time; polling can process an expired deadline later |
| Three RGB encodes | Means sum to 9.17 / 8.80 ms per accepted group | Existing writer performs three independent single-thread H.264 contexts serially |
| Three depth encodes and immediate checks | Means sum to 15.53 / 15.50 ms per accepted group | Includes PNG encoding, immediate decoding and pixel equality check; wrist alone contributes approximately 9.7 ms |
| Combined codec work | Mean 24.70 / 24.30 ms per accepted group | Excludes depth hashing, message serialization, MCAP writing and final verification; grouped-frame p95/max are not recorded |
| Writer queue | Peak 2 / 1 of 4; maximum delay 26.25 / 14.46 ms | No overflow; submission is nonblocking |
| Episode completion after 40-second capture | Approximately 7.5 / 8.4 seconds additional elapsed time | Flush, fsync and independent full-file verification are combined; cameras keep draining during completion |

The source-only nearest-frame receipt offsets and recording delivery maxima come
from different runs. Do not add their maxima and call the result an observed
end-to-end latency. They show a plausible tight budget requiring direct tracing.
SDK source timestamps do not independently establish physical exposure accuracy.

Of the missing-view rejections, 183 occurred in the first episode and 64 in the
second. Their median decision ages were 50.92 and 50.82 ms; all but the forced
end-of-episode boundary case were decided after the 50 ms wait. Rejections also
occurred late in the second episode, so startup alone is not an adequate account.
Excessive-skew (28/17) and reuse (2/1) need separate candidate/clock analysis.
The current archive does not retain every rejected anchor's other-view candidates,
so it cannot prove exactly which valid candidate arrived too late or was pruned.

## Existing concurrency and assessment

Three camera processes already run concurrently. The parent owns matching and
nonblocking submissions; one writer thread serializes codecs and MCAP output.
A finalizer thread waits for completion while the parent continues acquisition.
More encoding threads cannot change source timestamp skew or directly repair
the matcher's deadline decisions. Queue evidence does not establish codec
saturation, although 24-25 ms codec work leaves limited 33.33 ms full-rate margin.
Current acceptance rates also underload the writer relative to a complete stream.

## Proposed scope for alignment

1. Extend M07/M08/M11 timing evidence: per-frame SDK receipt, alignment completion,
   enqueue, supervisor receipt, matcher decision, candidate rejection cause;
   measure encode/check/hash/write stages and p50/p95/max. Keep diagnostics bounded
   and outside normal image payloads. Preserve original acquisition timestamps.
2. Replay actual arrival traces against the matcher to distinguish late delivery,
   polling/batch ordering, clock drift, pruning and unavailable unique candidates.
   Compare the current 50 ms wait with a proposed 75 ms wait under the same
   16.7 ms skew and no-reuse rules. Any production wait change needs alignment
   and snapshot traceability. Waiting is a camera collection concern and must not
   block future robot control.
3. Prefer prompt/event-driven supervisor wakeup if measured polling dominates.
   Preserve one matcher owner. Do not replace source timestamps with receipts
   or merely increase queues to hide stale input.
4. If full-rate writer measurements require more margin, benchmark removing the
   immediate depth decode/equality check from the hot path while retaining
   mandatory independent final-file pixel-hash verification and codec tests.
   Next consider a bounded encoder worker per camera, each owning its H.264
   state, with ordered results and one MCAP writer. No codec/quality change is
   implied, and concurrency is not implemented by this proposal.

Extend M08-A02.1 with measured deadline-boundary, batch-ordering and non-reuse
regressions using the saved physical traces. Account for every wrist anchor;
attribute each remaining rejection to concrete timing/candidate evidence. Check
full-rate writer headroom, unchanged depth integrity, bounded memory and cleanup.
Then run the M13-A03 20 x 40-second physical batch. Agree numerical grouped-output
tolerances before declaring acceptance; independent camera clocks and strict
non-reuse do not guarantee exactly 1200 valid groups in every 40-second window.

Evidence is under ignored `artifacts/physical-20260910/direct-rig-01/` and
`direct-shadow-01/`, including the extracted MCAP decision timeline. No production
code, image, station configuration or timing threshold changed during diagnosis.

## Aligned experiments and interim results

The user approved these experiments and requested a final resource/gate design
for alignment. Experiments use the existing image plus an explicit disposable
instrumentation wrapper, not a rebuilt release or modified production defaults.
The [resource and gate proposal](resource-gates.md) tracks the selected candidate.

| Experiment | Result |
| --- | --- |
| Instrumented baseline, 50 ms wait / 10 ms polling | 1127/1199 groups; 41 skew, 29 missing-view and two reuse rejections |
| Replay identical baseline arrivals at 75 / 100 ms | Both accept 1197/1199; 100 ms adds no benefit on this trace |
| Physical 75 ms wait / 10 ms polling | 1197/1200; remaining two reuse rejections and one end-boundary skew rejection |
| Physical 50 ms wait / 1 ms polling, first attempt | Interrupted by a user-confirmed cable/connection adjustment after approximately 36 seconds; explicit stale-source failure and retained partial; SDK cleanup reported a native allocator abort |
| Physical 50 ms wait / 1 ms polling, repeat | 1197/1199, two reuse rejections; zero source gaps/repeats; delivery p95 approximately 5.7-6.4 ms versus baseline 13.8-14.2 ms |
| 75 ms / 1 ms / final-only depth verification, CPU quota 4 and RAM 4 GiB, 2 x 40 s | 2394/2399 groups; all files verified; group processing mean 22.49 ms, p95 23.92 ms; queue peak one |
| Same candidate, initial 20-episode attempt | Interference stability FAIL: an additional in-container Python/OpenCV environment probe coincided with throttling, three D435IF source gaps, queue peak four and 109 ms delay; stopped after two completed episodes, preserving the active partial |
| CPU quota removed, RAM 4 GiB retained, 2 x 40 s | 2395/2399 groups; zero source gaps/repeats; mean group processing 22.08 ms, p95 23.13 ms; all files verified |

In the instrumented baseline, 69 of 72 rejected anchors had at least one
otherwise eligible candidate first observed after the 50 ms deadline. One had
candidates observed before the deadline but not yet submitted when the supervisor
batch expired it; the other two lacked an in-window or unused candidate. Replay
uses the same recorded push/advance/finish times and reproduces the original
counts before varying the wait. This isolates timing from changing scene content.

Docker exec event history places the extra environment probe approximately 0.16
seconds before the quota-run's first observed source gap. The earlier diagnosis
of a quota-associated stall remains supported, but it was an induced workload,
not an isolated collector overload. Do not claim that four cores are insufficient
for steady capture. Preserve this failure as interference evidence and keep
native import probes outside an active acquisition container.

PNG encoding itself averaged approximately 10.5 ms per three-view group in the
instrumented baseline. Immediate decode/checking duplicated work later performed
by mandatory final verification. Retaining only the final independent check
reduced hot-path group processing to approximately 22 ms in candidate runs.
Measured group processing includes hashing and message writing; MCAP message
serialization/writing averaged only approximately 0.03-0.05 ms per message.
Flush/fsync and full-file verification are separate, with verification dominating
the approximately 9-10-second inter-episode completion interval.

New durable regressions cover the measured candidate receipt/delivery offsets at
50 and 75 ms, rejection after the configured deadline, and valid PNG payloads
with a changed pixel in each camera. Every changed-pixel case fails final archive
verification and cannot become a completed episode. Mac Python 3.12 targeted
M08/M11 tests: **48 passed**; formatting passed. No runtime code changed.

### End-boundary correction within the aligned accounting scope

Full-source accounting during the long experiment found two in-boundary wrist
frames arriving at the parent after immediate finalization had begun. Neither
was counted as a matcher decision. Correct M09/M13 by retaining the fixed
40-second receipt cutoff while draining upstream transport for at most the
configured matching wait before requesting finalization. Continue to exclude
all frames received at/after the cutoff. Preserve the logical stop boundary
separately from the finalization request time. No camera or robot action extends
the acquisition interval. Test delayed pre-cutoff frames, exclusive cutoff,
bounded drain completion and unchanged asynchronous finalization, then repeat
physical acceptance with the corrected collection loop. This implements the
already aligned requirement to account for every wrist anchor.
During finalization, an in-boundary frame arriving after that drain budget
explicitly fails the session instead of disappearing. Acquisition failure and
file integrity remain distinct; no failed session can count as batch acceptance.

The uncorrected no-quota run completed all 20 recordings and verified every file,
with zero source counter gaps/repeats across approximately 30,000 frames per
camera. Full accounting found three unreported pre-cutoff wrist receipts in
episodes 0001, 0009 and 0014, so its acceptance accounting gate **FAILS** despite
99.771% overall grouping and clean sources. Its launcher also returned nonzero
after recording completion because the experimental shell script was edited
while still executing; this launcher failure is retained separately from the
completed recording report. Subsequent runners use a fixed versioned filename
and immutable mounted source files throughout the run.

The drain fix passed 59 targeted M08/M09/M11/M13 tests, followed by the six M13
tests after adding the reported drain limit. Changed runtime code passes Black
and Pylint 10.00/10. The physical correction test uses read-only `session.py` and
`shadow.py` overlays with revision `4f046a9-drain-working-tree-timing`; hashes of
both overlays, the probe and fixed runner are verified against the remote copies
and stored in ignored `artifacts/experiments/timing-20260910/drain-manifest.json`.

### Corrected full batch

PASS against the [proposed resource/gate configuration](resource-gates.md):
`batch20-drain-01` completed 20 exact 40-second episodes with exit code zero,
23,945 accepted groups from 23,995 wrist anchors (99.7916%), and no unaccounted
anchor identities. All files verified. Sources had zero gaps/repeats across
approximately 30,000 frames each. The maximum rejection streak was one; remaining
30 reuse and 20 skew exclusions obey the unchanged identity/skew contracts.
There were no missing-view rejections in this batch. Mean group processing was
19.91 ms, p95 22.15 ms, queue peak one of four, and no CPU throttling or OOM.
The resource document records full timing, memory, storage and acceptance bounds.
