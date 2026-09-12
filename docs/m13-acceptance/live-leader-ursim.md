# Historical Mac Leader / URSim Rehearsal (Retired)

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: retired on 2026-09-12 by explicit user direction. The Mac acquisition,
clock/file bridge and live rehearsal entry were removed. Historical commands
below are not runnable interfaces. Use the PC-only mainline
[native Isaac follower](../m14-digital-twin/native-teleop.md) instead.

## Historical evidence (superseded runtime)

Status: lightweight preview implemented; final installed short smoke PASS.
Manual joint-direction confirmation remains pending; this is not production
teleoperation or recording acceptance.

## Current scope: 2026-09-12 alignment

The user explicitly scoped Mac + URSim to manual motion-trend rehearsal, outside
production teleoperation and recording acceptance. This supersedes the full
Session/camera/recorder composition described in the historical sections below.
The existing live console command will select a simulator-only preview owner:
Space requests native follower HOME, then starts relative following, then stops;
the next Space requests HOME again. No camera, recorder, MCAP or ROS observer is
started. Host raw read evidence and a small rehearsal report remain disposable.

Idle input expiry waits for recovery. Fresh stationary input is required on each
explicit start. During following the rehearsal-only 250 ms source limit stops
motion; recovery never resumes motion or rebases an active interval. Protocol,
clock, identity and torque faults remain terminal. Keep the isolated official
URSim boundary, shared motion owner, relative mapper and conditioning. Production
Session, recording gates and Ubuntu hardware acceptance are unchanged.

Implementation: distinguish temporary view expiry from source faults; retain a
non-destructive bounded process cache; remove the Mac SDK busy-read loop; add a
small simulation-only keyboard owner; route live input to that owner; test idle
recovery, explicit engagement, stop/cleanup and isolation from recording; build
and smoke-test the installed image. Physical motor writes remain forbidden.
Manual direction/trend acceptance remains the operator's next action.

## Historical full-session scope (superseded for live preview)

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

Installed image: `ur12e-collection:live-leader`, linux/amd64, source `bafeb20`,
immutable ID `sha256:954b379d1e88869d7b3fdbcf39b32c13fd3c0b715e3e919bbc30d87f4bace41c`.
All 87 installed Python/schema files match the committed source. This is one
unified development/runtime image; official URSim remains a separate service.
No physical station deployment or old-image deletion was performed in this slice.

The first installed regression had two failures (469 passed, two host skips):
`test_readonly_two_episode_files_have_no_actions` reported camera IPC overflow
on `third_left`; `test_two_real_process_episodes_keep_one_rig` reported writer
`queued=4 + 1 > 4`. These existing Mac/amd64 queue failures are retained; all new
live-input tests passed. One unchanged full recheck follows. No queue/freshness
threshold was relaxed to obtain acceptance.

Unchanged installed full recheck PASS: 471 tests, two host skips (26.91 s).
The first two queue failures remain unresolved and are not represented as fixed.
The exact documented `--installed-package` live command also reached
`needs_home` with the physical leader and exited through Ctrl+C; no source
package overlay was used. Manual joint movement remains the next user gate.

## User-reported idle stale failure (2026-09-12)

Status: investigating and correcting the existing live-entry contract, explicitly
requested by the user. No frequency, freshness, motion or calibration change is
proposed. The reported run `live-leader-1789160484716764000` retained 905 complete
read-only acquisitions over 14.784 s, maximum gap 50.030 ms, no publisher fault
and only READ/Fast Sync Read traffic. Its console failed in `needs_home` before
an episode. The current report cannot identify where the valid view stopped
advancing. A one-slot multiprocessing queue is destructively drained by both
producer and consumer; this is a suspected cache handover race, not yet proven
as the cause of this particular run.

Repair scope: reproduce with staged freshness diagnostics; correct latest-view
handover if confirmed, retain source epoch/time and the 100 ms expiry, and add
regression tests for concurrent reads, delayed publication and killed/stalled
workers. Rebuild the same image tag after source tests; verify prolonged idle
and the existing simulator lifecycle before returning the command to the user.
No physical device writes or real UR control are authorized by this repair.

The diagnostic reproduction `live-leader-1789160848300937000` failed with
109.184 ms source age, 42.504 ms since the last delivered cache view, and only
0.203 ms in the caller's read. The publisher stayed healthy (maximum source gap
34.579 ms). The destructive queue replacement leaves a publication gap because
`multiprocessing.Queue.put_nowait` hands work to an asynchronous feeder; producer
and consumer also compete to remove the same item. The reported run lacked
these stage timestamps, so its exact scheduling interleaving cannot be recovered.

The replacement is a fixed-capacity shared latest view. The writer serializes
before taking a short lock, then replaces the complete payload and generation;
readers copy without consuming it. A reader never waits on the lock; contention
retains its prior source-timestamped view, which still expires after 100 ms. A
writer that stalls or exits holding the lock therefore cannot hang control or
refresh stale data. There is no queue feeder or remove-then-publish window.
Errors now include source, publication, validation and receipt timestamps to
locate any later stall. Native concurrency/expiry-related focused tests PASS
(26), including a process exiting while holding the publication lock.

The first shared-cache long-idle check still failed after about one minute;
its publisher remained healthy but had an 84.055 ms maximum acquisition gap.
At failure the last validated view was also old; non-destructive storage alone
is not sufficient evidence of a complete fix. This failed run is retained as
`live-leader-1789160945484066000`. Bulk memoryview copies replace Python ctypes
per-element copies inside the short critical section, and the bridge poll rate
is bounded to the existing 120 Hz command target instead of approximately
500 Hz. This reduces redundant filesystem traffic and lock contention without
changing the physical read rate or any freshness limit. Further runtime checks
are required before replacing the installed tag.

The optimized shared-cache run also timed out, with producer and consumer at
the same generation. This rules out consumer lock contention as the complete
explanation. A Docker exec stdio relay was then introduced to remove cross-host
filesystem reads from the high-rate path; it also had an initial timeout. Those
changes alone do not establish the root cause. The Mac publisher process was
measured at 69.4% CPU while idle. Inspection of the installed DYNAMIXEL SDK shows
a tight receive loop over a zero-timeout serial read, sharing the interpreter
with the publisher. A bounded readiness wait on Mac can yield that interpreter
while waiting for USB bytes; Linux's accepted acquisition path must remain
unchanged. Any such change requires read-only timing and CPU remeasurement.

A source-side issue was identified in the Mac receive path: the installed SDK
loops over `serial.read()` with `timeout=0`, occupying approximately 69.4% CPU
in the same interpreter as the publisher. `ReadPort.readPort` now waits up to
1 ms for descriptor readability on Darwin before performing the same read.
Already-readable descriptors return immediately; SDK packet checks, instruction
allowlist and timeouts are retained. Linux does not use this wait, preserving
its accepted 120 Hz read path. The Mac process measured approximately 7.4% CPU
after this change. The stdio experiment was removed; its patch/logs remain local.
Current repair candidates are the Mac readiness wait, non-destructive latest
cache with bulk copies, bounded 120 Hz bridge polling and stage diagnostics.


Repair validation remains incomplete: after the Mac readiness wait, the original
file-transport run `live-leader-1789161543725895000` lasted 122.889 s and then
failed the unchanged 100 ms input gate (publisher maximum gap 49.147 ms). The
recorded feed call took 32.414 ms; its selected source view became old across
publication/read/scheduling stages. The combined readiness-wait/stdio experiment
also failed, with a 103.625 ms source age while local feed reading took only
0.160 ms. Its physical source maximum gap was 33.709 ms. Thus CPU busy polling
and destructive cache handover are concrete issues, but fixing them or replacing
file transport does not establish a complete latency solution on this Mac.
Do not label the original user's exact interleaving conclusively identified.

The stdio experiment and its tests are retained only under ignored artifacts;
the working repair keeps the simpler existing transport, the Mac-only read wait,
non-destructive shared cache and improved timing diagnostics. Native full suite
PASS (474 tests, five skips, 14.16 s); lint PASS. No failed candidate image was
built or substituted for the installed tag, and no physical motor write occurred.

Historical question, now resolved by the alignment at the top: whether transient expiry in `needs_home`/`ready` should
be an input-unavailable state, with a fresh stable baseline required before
starting, instead of terminating the whole console. This would not relax active
teleoperation's 100 ms expiry, source identity/error checks or physical control
restrictions. The lightweight preview now implements this recovery behavior.


## Lightweight preview repair results

- Software PASS: 482 tests, five skips in the native full run; an additional
  relative-trend/no-initial-jump test also passes after that run. Tests cover idle
  recovery, unavailable/moving startup before SDK acquisition, active expiry
  stopping, no automatic resume, hard faults, report cleanup and routing without
  constructing the recorder. Production control/recording implementation is
  unchanged.
- Live source-overlay smoke PASS: `console-1789162443569649000` used the physical
  read-only GELLO and isolated URSim. Native HOME completed, a stationary leader
  drove 1,756 conditioned commands over 14.70 seconds, Space stopped, measured
  settling completed, and Ctrl+C exited. No camera or MCAP output was created.
  Host evidence: `live-leader-1789162443308397000`. This confirms wiring and
  lifecycle only, not operator direction acceptance or Ubuntu production gates.
- Installed replacement image and its smoke check: pending.

The same launcher command selects the lightweight preview when `--leader-port`
is supplied. Space: HOME -> ready -> following -> stopped/held -> HOME again.
If startup is unavailable or moving, stabilize the supported leader and press
Space again. If input expires during following, the simulator stops and remains
held; no automatic restart occurs. Ctrl+C stops active simulator control and
closes the reader. Hand-E is bypassed; the physical leader remains torque-off.


The first installed repair image (`a5f01073cda9`, source `e77dad5`) passed
486 software tests (two skips). Its exact-command smoke
`console-1789162637255711000` reached HOME and sent 3,134 commands over 26.18 s.
A real bridge expiry then invoked the intended stop and measured settling. The
next explicit Space successfully returned HOME; Ctrl+C exited. Record this as
PASS for expiry recovery, not sustained uninterrupted following.

Follow-up repair: the IO worker previously discarded acquisitions arriving
between call entry and file-read completion. It now publishes those original,
validated acquisitions immediately; the actual control consumer still applies
its own as-of-call cutoff and unchanged 100 ms expiry. Separate tests cover both
boundaries. This avoids an unnecessary old-view delay without retimestamping or
relaxing production gates. Final image/smoke results follow below.


The subsequent source-overlay smoke `console-1789162750566688000` still met a
100 ms expiry after 13.37 s (1,568 commands); it stopped and remained held rather
than terminating the console. Including acquisitions arriving during IO is a
correctness improvement, not a demonstrated cure for Mac scheduling jitter.
The preview now prints the stop reason and retains its timing detail. A proposed
250 ms rehearsal-only input deadline awaits user alignment; production input
expiry remains 100 ms. Do not claim sustained following has passed.


The user approved **250 ms only for Mac + URSim rehearsal** after the measured
100 ms pauses. The shared pure mapper/input accepts an explicit freshness policy
with its production default unchanged at 100 ms; only the simulation preview
passes 250 ms. Motion bounds, absolute acquisition timestamps, epoch/health
checks and no-automatic-resume behavior remain intact. No production entrypoint
changes its policy. Test both the production default rejection and explicit
preview acceptance of a 150 ms input, plus expiry beyond 250 ms.


An initial 250 ms source-policy run stopped in idle because its separate periodic
clock round trip still used 100 ms (`console-1789162913319814000`). Align the
rehearsal bridge's periodic deadline to the same 250 ms. Startup offset precision
still requires a best-of-five <=25 ms round trip, and periodic checks must
intersect the original clock bracket; no timestamp rebasing is allowed.


The next HOME attempt (`console-1789162952316204000`) timed out before motion
started; the physical publisher had no fault or writes. A concurrent unrelated
ARX5 training-test container was observed using 527% CPU and 3.59 GiB, while
URSim used 118% CPU and 1.34 GiB. This is a resource-contention observation, not
proof that it caused earlier failures. The unrelated workload was left intact.
Targeted regression PASS: 66 tests for input, preview, mapping and production
session; subsequent bridge checks PASS (44 tests); lint 10.00. Keep the aligned
250 ms policy and repeat the installed smoke without this competing workload.


Final image build: source `ed26219`, local `ur12e-collection:live-leader`,
linux/amd64, image ID
`sha256:80ac995dacda2403bd5815a5c2355cd63db48ac1366f62751fe6e4f112c2c508`.
Full installed software run: 487 PASS, two skips, one FAIL in the existing
`test_readonly_two_episode_files_have_no_actions` (four-frame writer queue
overflow). Keep this failure visible; do not relax the production recorder gate
or claim a clean production release from a Mac rehearsal image. Targeted
recheck and live preview smoke are recorded separately below.


## Final installed rehearsal result

- Targeted installed checks PASS: 79 tests, including the failed queue case on
  isolated recheck. The initial full-suite queue failure above remains recorded.
- Installed source hashes match the working package; the exact documented
  `--installed-package` command uses image `80ac995dacda` (source `ed26219`).
- Short lifecycle smoke PASS: `console-1789163306721676000` completed native HOME,
  22.82 seconds / 2,726 following commands, explicit Space stop, measured held
  state, and Ctrl+C cleanup. No camera, MCAP, ROS observer or physical motor
  writes were started. Publisher `live-leader-1789163306463607000` reports no
  fault and only read traffic. The leader was stationary; manual axis-direction
  and operator ergonomics remain NOT RUN.
- An earlier, longer final-image run `console-1789163172897940000` sent 8,709
  commands without leader expiry before URSim feedback stopped progressing.
  The shared controller faulted and stopped; its feedback gate is unchanged.
  This remains a known Mac/URSim limitation, not accepted sustained operation.
- All rehearsal clients/readers have exited. The existing official URSim
  container remains available. Production 100 ms input policy, recording gates
  and physical hardware authorization are unchanged.

Use the existing command with `ur12e-collection:live-leader`; do not rebuild or
synchronize this preview as evidence of Ubuntu production acceptance. Support
the unpowered leader, press Space for follower HOME, hold the leader still, then
press Space to start relative following. Move one joint at a time and observe
URSim. Space stops/holds; another Space requests HOME. Ctrl+C exits. No gripper
actuation is simulated by this entrypoint.
