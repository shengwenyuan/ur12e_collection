# M09 Physical Teleoperation Recording Integration

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / physical acceptance pending, 2026-09-13.
Dependencies: M03/M04/M06 control, M07/M08 cameras/grouping, M10 semantics,
M11 persistence. The operator requested this increment after the accepted
control-only physical loop, with one episode followed by a 2–3 episode session.

## Aligned scope and implementation

The native Teleoperation remains the sole motion owner. A recording coordinator
owns preparation, common acquisition boundaries, finalization and disposition.
Persistent Recorder owns cameras and off-loop codecs/writing/verification.
Independent output-only Feedback workers record UR at 125 Hz and raw Hand-E
polls at approximately 10 Hz. Arm commands remain 120 Hz; they are not sampled
at the 30-Hz camera group rate. No additional RTDEControl interface is created.

Cameras start before the SDK connection. Independent feedback workers start after
that connection, before leader acquisition and watchdog-driven motion, avoiding
startup queue overflow. All readers drain through HOME, waiting and finalization.
The launcher exposes the USB bus and only RealSense-labelled V4L2 nodes.
The launcher uses an 8-GiB memory ceiling, 512-MiB shared memory, shared camera
slots, three encoding and three verification workers, and one BLAS/OpenMP thread.
The physical launcher still checks a direct local Ethernet route to the robot.

Prepare a fresh episode writer before attempting engagement. The leader reference
must pass stability checks; then record an acquired authority event at the same
boundary that seeds following. An unstable reference retries without new motor
commands. If the gripper is not open, open it manually and press Space again.
Each episode captures a fresh leader/gripper reference; no reference is rebased
while following. HOME does not open Hand-E or command leader motors.

Space during recording dispatches stop first, then drains independent feedback
through its exclusive cutoff. Both FIFO readback streams must pass the cutoff
before the tail is flushed. Only measured hold permits finalization. No next
HOME or episode starts until independent MCAP verification and atomic commitment
complete. The session report preserves the stop-confirmation receipt separately
from the demonstration cutoff. Feedback batches split into at most 64 records
without changing the writer queue capacity or loss policy.

## Operator interaction

- Space: HOME; at READY prepare/start; during recording stop and save; after
  verified save request HOME. Another distinct Space starts the next episode.
- `a`: stop/discard an active episode, or mark the last completed episode discarded
  while idle. Keep verified files and an explicit disposition; task success stays
  unknown. Camera workers do not restart.
- `q`: normal session end. Stop an active episode, wait for hold and verified save,
  then close. During preparation, abandon the unstarted partial. This is the
  implementation default proposed to the operator; no contrary preference was
  received. It is independent of keyboard debounce.
- Ctrl+C / EOF / SIGTERM: interrupt and revoke following. Active output remains
  an incomplete partial; already committed episodes survive. Exit never requests
  HOME or releases the grasp. Existing 30-second post-stop observation remains.

A session directory contains `session.json` and `episode-NNNN/` directories, each
with MCAP, metadata and outcome JSON. File/codec state rotates per episode;
camera and readback processes remain connected. An empty/failed/unfinished episode
must never be presented as successfully saved. Required recorder/readback errors
propagate through motion-owner cleanup. Reader cancellation is nonblocking before
the physical stop/hold cleanup, preventing shutdown queue overflow.

## Data contract

The independent archive validator requires the physical episode's actual sent
command count divided by its acquisition interval to exceed 30 Hz. Configured
120 Hz is not evidence of the delivered rate.

Snapshot declares backend UR, Hand-E URCap, actual device identities and image ID,
plus limits, guards, transport and gripper configuration. The station's active
leader backend is `dynamixel_readonly`; the acquired event embeds calibration,
raw baseline, mapping and the relative gripper reference. Archive verification
reconstructs arm and gripper intent and checks conditioned command derivatives.

Retain paired actual arm state/UR readback and independent raw Hand-E polls with
original receipt/controller clocks. Hand-E has no device timestamp. LeaderIntent
contains mapped raw gripper request; SentCommand contains only the acknowledged
arm target, because asynchronous/coalesced gripper delivery has no arm-synchronous
acknowledgment. Training normalization and LeRobot export are out of scope.

The operator declared a 127-mm TCP extension. Local-axis/orientation and whether
it is active in the UR installation remain unconfirmed. Current recordings retain
base-to-active-TCP readback; do not fabricate flange pose or verified TCP offset.
This does not block joint-space recording, but flange-pose acceptance stays open.

## Software and physical acceptance

- M09-A01/A03/A04 software: PASS for preparation before engagement, unstable
  reference waiting, stop-before-IPC, FIFO tail exclusion, finalization barriers,
  repeated-episode resource reuse, discard/normal quit/interruption semantics.
- M10-A01/A02/A03 software: PASS for separate intent/sent/actual values, immutable
  gripper reference and raw mapping audit, source identity binding and independent
  120-Hz command / 125-Hz feedback / 10-Hz gripper fixture streams.
- M11-A01/A02/A03/A04 software: PASS for three consecutive synthetic-input episodes
  using real codecs, writer and independent decoder; per-episode RGB decoding,
  pixel-exact depth verification, record counts and atomic completion. Synthetic
  evidence is explicitly simulated; it is not a hardware timing benchmark.
- M09-A02 physical and combined M09/M10/M11 recording: NOT RUN at this revision.
  The operator deferred additional physical stop/fault/contact tests. Guards are
  retained; the emergency stop button is not evidence that these gates passed.

Before delivery, run `scripts/check` in the provisioned development environment
and offline tests in the built Linux image. Record actual results below. Keep
hardware acceptance separate from both software runs.

## Lab acceptance sequence

Confirm current camera serial-to-role assignments. The historical binding is
D405 wrist 260522273667; D435IF left 327122073926 and right 327122075735, with
left/right physical placement still requiring operator confirmation.

The operator launches with `--record-station`, `--record-output`, `--task` and
`--operator-approved`. First collect a short single episode, then 2–3 episodes
around 40 seconds each in one process. Space stops, wait for `Saved ... MCAP
verified`, Space returns HOME, and the next Space records. Finish with `q`.

Inspect every stream, actual command rate above 30 Hz, camera grouping/rejections,
source continuity and process resource statistics, queue peaks, file size and
stop/commit times. Independently verify all MCAPs and JSON boundaries. Demonstrate
that frame sequences and camera processes continue across episodes. Keep the
16.7-ms pairing threshold and 75-ms matching wait unchanged. Do not lower gates
because combined physical recording has not yet been exercised.

## Local results, 2026-09-13

Full offline suite: 595 PASS, 5 environment-dependent SKIPs. Black checked 192
files; project Pylint PASS, 10/10. Includes 13 coordinator tests and explicit V4L2 device exposure checks. No robot, Hand-E or leader control was sent.
The earlier teleop rate/reference adjustments were separately committed as
`8e34182` before this recording integration. Linux image and physical results
will be recorded separately from these local checks.

PC output-only enumeration PASS: the three expected serials are present as a
non-root container user. D405 reports USB 3.2; both D435IF devices report USB 2.1.
USB-only exposure initially found no devices; adding the existing RealSense V4L2
exposure policy resolved discovery. This is discovery evidence, not RGB-D
streaming, camera-role placement or combined physical recording acceptance.

## Image delivery and PC checks, 2026-09-13

Implementation revision: `a4ac32d`. Cached Linux/amd64 build from the existing
`5185ee5` base installed only the new local wheel; no dependency download.
Mac Docker Desktop and Ubuntu `ur12e-collection` now resolve
`ur12e-collection:physical-teleop` to the identical image:
`sha256:0ae98368bd66731833f36373cb9d252fd48e2bc68747f102e2bd578e3bc86074`.
All 108 installed package source/schema hashes match the local tree; the deployed
PC host package also matches. The independent Isaac environment was not changed.

Linux image focused regression: 158 PASS on Mac Docker and 158 PASS on Ubuntu,
with networking disabled and no physical device mounts. Coverage includes
collection lifecycle, physical configuration/launcher, MCAP/control contracts,
leader audit, snapshots and storage. This tests the installed image package.

PC camera-only check: PASS for startup and ten seconds of continued recorder
health with all three live sources. Executed non-root, network disabled, no
leader serial connection, no UR/Hand-E reader startup and no control interface.
The check did not begin an episode or establish grouped-image/teleop throughput.
Two D435IFs remain on USB 2.1; D405 is on USB 3.2. Physical left/right placement
and the active TCP transform remain operator confirmations. Combined real
recording and the revised motion rates remain NOT RUN.

Staged station file:
`~/ur12e-real-teleop/config/local/recording.station.json`. It preserves the prior
explicitly unconfirmed third-view assignment rather than claiming new geometry.
After confirming those roles, the operator starts:

```bash
cd ~/ur12e-real-teleop
python3 scripts/teleop.py \
  --config config/teleop.ur.json \
  --image ur12e-collection:physical-teleop \
  --operator-approved \
  --record-station config/local/recording.station.json \
  --record-output artifacts/recordings \
  --task teleop_lab_acceptance
```

For a single episode: Space HOME, Space record, Space stop, wait for verified
`Saved`, then `q`. For the following 2–3 episode session, repeat Space HOME and
Space record only after each verified save; `q` ends the session normally.
Ctrl+C interrupts active output instead of certifying a complete episode.

## Teleop rejection recovery increment, 2026-09-13

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / physical acceptance pending. The operator requests independent arm/gripper input guards and
an interactive collection process after teleoperation rejection. Do not route a
rejection directly into blocking process cleanup. Keep actual motion revoked
while the collection loop accepts save, discard and quit.

Guard configuration selected for this fix: retain 180 degrees/s for the six arm input encoders and
use an independent 720 degrees/s gripper-lever input bound. Both retain two counts
of quantization allowance. Hand-E SPE/FOR and follower motion/stop limits do not
change. Report the offending axis, counts, elapsed time and applicable bound.

Recovery design: one fault boundary ends the demonstration interval; supervised
stop/hold progresses without blocking keyboard processing. Input-only rejection
may proceed to a new HOME/reference after confirmed stop and episode disposition.
Failed robot transport/state or required recorder/readback resources remain
unavailable for renewed motion; retaining an interactive process does not grant
permission to resume a failed control connection. Never recreate a control
interface automatically. Ctrl+C remains an interrupt.

The implementation default for the requested save/discard/quit choices is:
Space saves only a verifiable pre-fault interval,
with its interruption reason; a discards; q saves verifiable output and exits.
Invalid or incomplete data remains partial. Failed dependencies cannot be turned
into a successful demonstration by an operator save request. Preserve persistent
healthy camera resources between episodes.

Acceptance: separate arm/gripper rate and encoder-wrap/jump cases; detailed
rejection evidence; responsive operator choices during stop/hold; save/discard/
quit after rejection; no resumed servo before an explicit HOME/new reference;
unhealthy feedback/recorder paths retain partials and prevent unsafe restart.
No physical motion is authorized by this implementation request.


Software acceptance for this increment:

- `M04-A03`: PASS. Six-joint input retains 180 degrees/s; the gripper lever has
  its own 720 degrees/s limit. A 60-count change over 8.33 ms passes only for the
  gripper; larger jumps remain rejected with raw before/after and timing details.
  Follower rates, gripper output limits and startup reference checks are unchanged.
- `M09-A01/A03`: PASS. Rejection revokes following before storage handling, keeps
  stop supervision and operator input running, preserves existing discard/quit
  intent, and never starts HOME or a new reference automatically. Cancellation
  closes the per-episode writer asynchronously and leaves camera resources alive.
- `M09-A04`: PASS. Tests cover save, discard and quit during stop, preparation,
  finalization and resource failure. An interrupted valid prefix retains its
  reason in authority/outcome metadata. Failed feedback, recorder or stop
  confirmation cannot be certified by pressing save; incomplete output stays
  partial and the session permits orderly exit without reconnecting control.
- Real-codec regression: PASS. Cancelling prepared and recording writers leaves
  partials, then the same capture object writes and independently verifies a new
  interrupted MCAP interval. Cancellation polling is nonblocking with a five-second
  cleanup deadline. Existing three-episode recording tests also pass.
- Local checks: `scripts/check`, 610 PASS / 5 environment-dependent SKIPs; Black
  checked 192 files, Pylint 10/10. An initial sandbox run failed five POSIX shared
  memory/child-interrupt cases; rerunning with OS shared-memory permission passed.
- Physical rejection/recovery acceptance: NOT RUN. No robot, gripper or leader
  control was sent. The existing final session shutdown still performs its
  stop/hold cleanup after quit or Ctrl+C; rejection alone no longer enters it.
