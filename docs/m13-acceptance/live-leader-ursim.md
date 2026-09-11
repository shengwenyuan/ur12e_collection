# Live Read-Only Leader to Isolated URSim

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented; live-source lifecycle checked, installed-image and manual acceptance tracked below.
On 2026-09-12 the user assigned LeRobot conversion to another repository and
requested manual physical-leader / URSim follower validation before proceeding.
Reuse the aligned episode-relative mapping, HOME, signs-under-verification,
read-only motor boundary, keyboard lifecycle, and isolated simulator controls.
No new physical motion authorization is inferred.

## Scope

1. Remove the LeRobot CLI/export implementation, optional exporter requirements
   and exporter-only tests. Retain neutral MCAP read/hash helpers used by audits,
   replay and the M14 trajectory interface. MCAP plus JSON is this repository's
   final collection artifact; external conversion owns training projections.
2. Add an explicit live-leader option to the existing simulator console launcher.
   Mac owns the verified U2D2 serial device using the existing read-only Reader;
   Docker retains the existing isolated URSim Station, Session, conditioning,
   watchdog, limits, camera fixtures and MCAP recorder. No native Mac UR SDK or
   general host network route is added to the simulator client.
3. Transfer a bounded recent-sample window through an atomic local file mounted
   into that one run. Preserve source epoch, sequence, raw counts and timestamps.
   A nonce-bound request/reply clock handshake brackets the Mac-to-container
   monotonic offset. Use its conservative lower bound; bound round-trip
   uncertainty and periodically verify the original clock bracket. Never assign
   a fresh acquisition timestamp merely because an old file was read again.
4. Record original read-only leader JSONL on the host. Retain a bounded recent
   window spanning the existing 40 ms startup stability requirement (four samples
   at the new 120 Hz rate are insufficient). The consumer checks source/health,
   torque-off state, expiry, chronology and the existing 100 ms input limit.
   EOF/publisher loss, stale file, clock discontinuity and source restart fault
   the session; no silent fallback to Wave or recorded input.
5. Use an explicit simulation calibration file with provenance and candidate
   directions derived from the already reviewed operator reference. It does not
   attest physical calibration. The operator manually supports the torque-off
   leader; no motor write/HOME/HOLD coordinator is created. Hand-E is bypassed.
   Space retains the existing HOME/start/stop/review transitions; Ctrl+C stops
   URSim and closes local readers. The first Space requests follower HOME only.

## Acceptance

- Export command/dependencies gone; neutral MCAP verification/replay/twin readers
  and existing snapshots remain valid. Do not delete user recordings or datasets.
- Deterministic bridge tests: clock uncertainty, stale/replayed files, future or
  reordered acquisitions, epoch changes, hardware errors, torque-on state and
  stable-reference timing; calibration/sign and shared conditioning reused.
- No writer/control/IO API reachable from the physical leader publisher; no
  default/external route or arbitrary follower address in the simulator client.
- Existing software regression plus installed-image checks. A read-only live
  bridge smoke may observe the connected leader; simulator fixture checks may
  move URSim. Physical UR control and all motor register writes are forbidden.
- Deliver one exact terminal command and keyboard expectations. Do not claim
  human directional or ergonomics acceptance until the user manually operates
  each permitted joint and confirms URSim response. ID3 cable remains unresolved;
  no active leader elbow command is introduced.

## Engineering boundaries

The bridge is a local rehearsal adapter, not a production network telemetry
service. It uses no listening socket, exposes no robot control port and does
not make Docker Desktop a production acquisition requirement. Preserve current
motion bounds and actual input timing; Mac read rate may differ from Ubuntu's
accepted 120 Hz. No additional camera/long-load campaign is required for this
small entrypoint; synthetic camera provenance must remain explicit.

## Implementation and evidence (2026-09-12)

The live entry is implemented. A Mac serial owner publishes read-only samples;
a separate Linux process validates the bridge and supplies a one-slot latest
view to the existing Session. Native SDK calls must not starve bridge processing
through the Python GIL. The original source JSONL retains all host acquisitions;
a repeated control view keeps its original source sequence/time. No Wave fallback,
leader HOME/HOLD object or physical motor command transport is selected.

Messages use unique atomic temporary files and a fixed 16 KiB padded size. Two
initial variable-size bind-mount runs produced truncated JSON; unique temporary
names alone did not resolve it. Fixed-size messages passed the subsequent read
and console checks. File-size metadata coherence is a suspected mechanism, not
an independently proven Docker defect. A publish racing a read is validated
against the post-read clock; only acquisitions available at the caller's timestamp
are returned. No timestamps are rewritten to satisfy this rule.

Startup clock calibration requires a best-of-five round trip <=25 ms. Periodic
checks allow <=100 ms, matching source expiry, and verify the original bracket
without rebasing timestamps. An initial 25 ms periodic deadline failed under the
full simulator workload. The existing 100 ms acquisition freshness limit,
40 ms/two-count startup stability requirement and follower motion limits remain
unchanged. Bridging first ran inline, then in a thread; HOME/SDK handover tests
exposed stale/gapped views, so the final consumer is process-isolated.

Read-only bridge PASS: 10 s at 61.482 Hz (maximum gap 33.680 ms), followed by a
30 s run at 61.481 Hz (maximum gap 41.670 ms). An intervening 30 s attempt failed
with a source timeout (`There is no status packet!`); this physical serial fault
remains retained and is not declared repaired by a recheck. A concurrent launch
was correctly refused by the exclusive serial lock; no second reader opened.
Logs remain under `artifacts/live-leader-validation/`.

M04/M09/M10/M11/M13 live-entry slice PASS with physical stationary leader and
actual isolated URSim: `console-1789160002178464000` completed HOME -> ready ->
recording -> stopping -> held -> Ctrl+C. One 3.092 s episode contains 371 sent
commands, 371 leader intent records and 93 RGB-D groups. Every RGB frame decoded
and every depth hash verified; MCAP size is 2,813,971 bytes. Raw leader evidence
is in `live-leader-1789160001920767000`; its source has no motor writes. These
runs used a frozen current-source overlay on the prior accepted runtime image.
This proves the real-input path and lifecycle, not manual direction acceptance.

The local simulation calibration keeps the previously reviewed HOME counts and
candidate signs. Its explicitly unverified +/-4096-count input intervals permit
the current resting pose for relative mapping; they are not accepted physical
mechanical limits or motor goal ranges. Follower limits remain unchanged. The
operator must still support the torque-off leader and respect the unresolved
ID3 cable constraint. Source loss stops the session; restart is explicit.

## Manual rehearsal

From the repository root, with the physical leader supported:

```bash
.venv/bin/python scripts/sim_control.py console \
  --client-image ur12e-collection:live-leader \
  --installed-package --client-memory 5g \
  --leader-port /dev/cu.usbserial-FTBEQCDG \
  --leader-calibration config/local/gello-live-sim.json \
  --manual-support
```

The local calibration file is deliberately Git-ignored; another checkout must
provide its own reviewed simulation configuration. The baud argument defaults
to the existing 3 Mbps setting and does not change motor registers. Do not run
another serial reader simultaneously. Observe URSim at
<http://localhost:6080/vnc.html>.

1. Wait for `needs_home`, then Space requests follower HOME only.
2. At `ready`, support and keep the leader still, then Space begins leading and
   recording together. The current leader pose becomes the immutable episode
   baseline; its absolute pose need not equal follower HOME.
3. Move one permitted axis at a time and inspect the corresponding URSim joint.
   Hand-E is bypassed; three camera sources are explicitly synthetic.
4. Space ends leading/recording and waits for `held`; another Space requests HOME.
   `a` discards the episode. Ctrl+C stops and exits; it does not request HOME.

Manual joint-direction/ergonomics acceptance: NOT RUN; reserved for the user.
Physical UR, Hand-E actuation, leader torque/HOME/HOLD: NOT RUN and not authorized.

Software acceptance: native full regression PASS (468 tests, five environment
skips, 10.81 s); Black and Pylint PASS (10.00, no findings). The initial restricted
run could not allocate POSIX shared memory or execute signal/process tests;
rerunning with the required local permissions passed. New tests cover source
chronology, stale/replayed views, clock bounds/discontinuity, fixed-size framing,
read/publication races, startup stability, isolated-worker cleanup, source fault
propagation through console cleanup, and removal of the export CLI. Independently
reopening the completed live MCAP passed all RGB/depth checks and confirmed
physical-live-leader provenance plus the immutable per-episode baseline.
