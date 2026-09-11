# Native-Rate Feedback and Action Recording

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned shadow correction; high-rate training projection remains a
separate design item. The user requested shadow alignment with the latest rate
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

M11: the current LeRobot RGB/arm export is explicitly camera-anchored at 30 Hz
and therefore discards intervening action rows in that projection. Raw MCAP
retains them. This existing export is not an accepted high-rate training path.
A later aligned projection must preserve high-rate action sequences, either
using timestamp-indexed action windows alongside 30 fps images or a documented
high-rate row timeline with explicit image references. Do not encode duplicate
images at 120 fps merely to make metadata frequencies equal. The dataloader and
model's action horizon must have a known physical duration. No exporter behavior
is silently changed by this shadow correction.

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
has been enabled. The existing camera-anchored LeRobot export remains 30 Hz
and is explicitly not accepted as the future high-rate action consumer.
