# Native-Rate Feedback and Action Recording

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented; software and physical 125 Hz shadow recheck PASS. Initial
Mac replay and physical camera failures remain unresolved. High-rate training
projection belongs to a separate repository. The user requested shadow alignment with the latest rate
requirements on 2026-09-12. The already selected 120 Hz commands / independent
125 Hz feedback contract remains valid; physical control is not authorized.

## Frequency decision and semantics

- Physical leader and generated/sent arm targets: 120 Hz requested, actual
  timestamps and actual counts archived independently of camera grouping.
- UR observations: 125 Hz output subscription and distinct received controller
  states retained in shadow MCAP, replacing the deliberate 30 Hz extraction.
- RGB-D: 30 fps; Hand-E measured raw state: approximately 10 Hz GET polls.
  Gripper requests and measured closure are distinct channels; never present
  repeated old raw gripper feedback as a fresh 120/125 Hz measurement.
- Shadow has observations only. It must not synthesize actions from follower
  positions. Controlled MCAP already stores independently timed leader intent
  and sent commands; action requests must remain distinct from feedback.

120 Hz actions divide the nominal 30 fps camera cadence into four intervals;
125 Hz is the already verified controller output rate. Matching numbers is not
necessary for timestamp association. Increasing the action target to 125 Hz
would exceed the selected 120 Hz leader cadence without establishing more
independent leader information. Preserve the tested 120 Hz action target.
Do not interpolate raw archives or insert samples to satisfy a frequency gate.

## Scope and implementation

M03/M13: use one shared UR output-rate constant. In the output-only worker,
inspect the SDK cache at a bounded 1 ms interval and emit each new controller
timestamp once; cached packets do not refresh liveness and backward timestamps
remain faults. The previous standalone 125 Hz diagnostic proved this approach
on the actual station. This is cache inspection, not a 1 kHz network request.
Keep existing bounded queues, freshness limits, stop behavior and GET-only
Hand-E transport. Synthetic feedback should exercise the new nominal cadence.

M10: new shadow snapshots state 125 Hz. Continue accepting historical 30 Hz
snapshots without relabeling them. The observer rate is a target, not a promise
that every packet was retained: actual timestamps/counts/gaps determine success.

M11: MCAP preserves high-rate actions independently of the 30 fps images. On
2026-09-12 the user assigned LeRobot conversion to a separate repository; the
former camera-anchored exporter was removed. External consumers own timestamp
association, action windows and a known physical duration for the model horizon.
Do not rewrite or interpolate the raw collection archive to match image cadence.

## Acceptance

1. Deterministic output-only fake receiver emits 125 distinct states over one
   nominal second; cached polls create no duplicates and rollback still faults.
2. Historical 30 Hz and new 125 Hz feedback snapshots validate unchanged; new
   shadow recordings declare 125 Hz and retain independent state records.
3. Existing source/queue/fault/shutdown and full regression tests pass without
   weakening deadlines or bounds. No control or IO interface is instantiated.
4. Reuse one 40-second physical read-only combined workload if devices remain
   connected: inspect actual MCAP state count/rate/source gaps, not a sidecar
   alone; decode RGB and verify depth hashes. Keep image/source provenance exact.
   Otherwise record hardware acceptance as NOT RUN and validate using software.
5. Build and validate the resulting candidate before delivery. Neither simulated
   actions nor a read-only shadow result establishes physical control acceptance.


## Software acceptance

Native focused feedback tests PASS (34); full regression PASS (453 tests,
five environment skips, 10.78 s). Black and production/script Pylint PASS
(10.00, no findings). Added cases prove retention of every 8 ms packet under
1 ms cache polling and preservation of both historical 30 Hz and new 125 Hz
snapshot values. Existing cached-packet and rollback cases remain passing.
Installed-image and physical MCAP rate evidence follow; no physical control
has been enabled. The historical camera-anchored exporter was later retired; external conversion
owns high-rate training semantics.


The first Mac/amd64 installed suite failed in the unchanged, feedback-free
three-producer camera replay fixture: `queued=4 + 1 > 4` during a 0.25-second
run (455 passed, two skipped, one failed; 27.89 s). The native suite passed.
This resembles prior Mac queue failures but its cause is not established.
Keep the failure and perform one unchanged full recheck; do not increase queues
or claim a fix from a later pass. The PC leader has now been disconnected, so
new-image hardware validation can cover cameras/UR/Hand-E only. The previous
120 Hz leader combined-load result is retained with its original image identity.


Unchanged full installed recheck PASS: 456 tests / two host skips (28.65 s).
The initial failure remains unexplained. Source is committed as `c6fa8e5`;
its candidate includes the shared 125 Hz output-rate constant, cache deduplication,
new snapshot rate and the synthetic feedback cadence. Hardware result follows.


Ubuntu candidate checksum/load/mount checks and installed regression PASS
(456 tests / two skips, 14.16 s). First physical shadow FAILed after about 19 s
with `camera counters restarted`; this existing error also covers non-increasing
camera timestamps, so it does not prove a USB reset. Existing logs do not retain
the offending source/deltas; kernel query showed no recent entries. No full
episode was committed. The partial run had 2,380 observed UR samples, no reported
feedback error, and no writer backlog at failure. Preserve the failed run and
perform one fresh unchanged 40-second check; never merge partial attempts.
The initial error's root cause remains unresolved if the recheck passes.


## Candidate identity

Source: `c6fa8e5`. Image: `ur12e-collection:shadow-native125`, linux/amd64,
immutable ID `sha256:3a6d698a36e58fbd6663b7d0bee0cf4e768f8e7db657a51c13884888f3f7635b`. All 85 installed production Python/schema
files match source. Checksummed bundle is available locally at
`artifacts/releases/ur12e-native125-c6fa8e5` and on the PC at
`~/ur12e-native125-c6fa8e5`. Exact OS/Python packages are included. The accepted
current deployment/configuration remains unchanged; this is a candidate whose
physical acceptance and retained failures are recorded above/below.


## Physical MCAP acceptance

Fresh unchanged recheck PASS: one 40-second episode, independently reopened and
verified. The MCAP itself contains 5,000 UR feedback records: controller rate
125.000 Hz, every source gap exactly 8 ms, zero missing 8 ms slots, host receipt
rate 125.000139 Hz and maximum receipt gap 9.100 ms. Snapshot `ur_read_hz` is 125.
There is no additional RTDE diagnostic observer and no 125 Hz sidecar used to
establish this result. The 392 measured Hand-E states remain approximately
9.801 Hz, FLT=0 and STA=0; no activation or actuation was performed.

Camera grouping is 1,197/1,200 (99.75%), maximum one consecutive rejection;
all three sources have zero color/depth gaps or repeats. Every RGB frame decodes
and every depth hash verifies. MCAP size 456,514,289 bytes; writer queue peak 1/4,
feedback queue peak 5/64, maximum writer queue delay 37.314 ms. No queue limit,
wait/freshness threshold or motion setting changed. No action/control records
exist in this read-only shadow. The disconnected physical leader was excluded;
its previously measured 120 Hz workload remains separate evidence.

Failed data remains at `/var/lib/ur12e-collection/data/native125-shadow-20260912`.
Passing data and `file-audit.json` remain at
`/var/lib/ur12e-collection/data/native125-shadow-recheck-20260912` on the PC.
Local reports, code/build/test logs and independent audit are under
`artifacts/readonly-full-20260912/` with the `native125-` prefix. No failed data
was overwritten or combined with the passing episode. No physical control was
sent. The first camera counter/timestamp failure and Mac fixture queue failure
are not declared fixed by their later passing rechecks.
