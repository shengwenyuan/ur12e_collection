# M14: Native Follower Selection and Isaac Teleoperation

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: accepted for the native arm-only kinematic teleoperation scope,
2026-09-12. Gripper control is the next increment.

## Alignment and scope

The user explicitly requires a PC-only mainline topology: physical GELLO USB
input drives a native simulated follower; URSim is reference implementation and
regression coverage only. No Mac acquisition, SSH forwarding, URSim proxy or
browser observation bridge is part of this runtime. The user selected kinematic
execution for the first Isaac follower, with physics/contact validation deferred.

The shared teleoperation domain owns calibration, episode-relative reference,
conditioning, limits, HOME/follow/stop transitions and fault handling. A follower
backend owns execution and feedback. The active simulated follower is configured
as `isaac_kinematic`. Existing UR control remains separately disabled. Future
real-plus-sim operation must send only commands accepted by the primary owner to
bounded optional twins, preserving separate identities, clocks and feedback.

## Native interfaces

- Native GELLO sampling remains 120 Hz through the read-only leader source.
  Startup stability spans at least 40 ms; mainline input freshness stays 100 ms.
- The common owner consumes backend-neutral motion readiness. UR status decoding
  stays specific to UR feedback; Isaac never invents robot/safety program codes.
- Follower operations are asynchronous move, servo target, stop, heartbeat,
  readback and close, sharing the existing control owner and conditioning.
- The Isaac application consumes a local Unix-domain endpoint configured by
  path. It applies kinematic state to the configured scene and returns executed
  positions, velocities and an explicit simulated clock/identity. No network
  host, controller SDK, fake UR feedback or Mac clock handshake is involved.
- The control loop runs independently of rendering. The renderer consumes bounded
  input and publishes only actually applied kinematic state. Display sampling
  is not fabricated as 120 Hz feedback. The simulation profile allows 500 ms
  follower feedback age; physical limits and freshness are not relaxed.
- HOME uses a speed/acceleration-bounded kinematic trajectory. Stop freezes the
  kinematic pose; it does not model physical braking. Commands expire, old
  ownership epochs cannot resume motion, and producer loss stops execution.
- Scene assets and FK remain in the separately configured scene project. Runtime
  control and follower lifecycle live in the collector package. Paths resolve
  from configuration, and local mounts preserve the same interface.
- Camera/MCAP recording remains separate from this initial control-only launch.
  It must never claim a recorded episode or production collection acceptance.

## Steps and acceptance

1. Retire the temporary observation bridge and Mac runtime. Preserve reusable
   scene topology/pose helpers and existing independent regression tools.
2. Introduce native follower feedback/selection and Isaac kinematic execution;
   reuse the common owner without backend conditionals in teleoperation logic.
3. Add a mainline configured teleoperation entry with native leader acquisition,
   no leader motor writes, and separate optional twin dispatch responsibility.
4. Validate known poses, timing, HOME bounds, stop/watchdog, exclusivity,
   late/reordered commands, feedback truthfulness and relocation in software.
5. Deploy to the Ubuntu PC, run Isaac render checks and read-only leader checks,
   then hand off the explicit teleoperation launch to the user.

M14-A01: command intent, primary accepted command and executed simulated feedback
stay distinct and retain source identity, epochs, time and units. M14-A02: optional
twins cannot delay or own primary control. Native Isaac as primary is required
feedback: loss causes a latched stop, never silent continuation. Keep M06 motion
and M04 source tests as regression gates. Human directional acceptance is PASS by the user confirmation recorded below.

No physical follower commands or leader torque/HOME/goal writes are authorized.
The current physical leader is connected to PC `/dev/serial/by-id/` and its
permissions must be handled through the existing restricted container device
mapping, not a world-writable device or an assumed sudo grant.

## Implementation and results

- **M14-A01 PASS, software and actual Isaac:** common control owner consumes
  backend-neutral readiness without inventing UR robot/safety codes. Native
  six-axis signed/mixed trajectories, bounded HOME, executed readback and stop
  pass. The visible Ubuntu scene test sends 1,835 host samples and observes 178
  distinct applied updates; display is approximately 12 Hz under this GUI load,
  independently of the approximately 120 Hz producer. Configured display 30 Hz
  is a cap, not achieved/rendered-rate acceptance.
- **M14-A02 PASS, software:** optional twins use independent one-slot dispatch;
  slow consumers and failed primary sends cannot block or falsely advance the
  primary. Unix stream framing, owner identity and watchdog tests pass. This
  does not establish two live followers or real-plus-sim hardware acceptance.
- **M04 PASS, current PC read-only check:** after the user powered the leader
  and changed FTDI latency from 16 ms to 1 ms, 360 samples over 3.003 s measured
  119.88 Hz at 3 Mbps. All seven torque/status error fields were zero. The prior
  no-status-response test is retained; no single physical cause was established.
- **M06/M14 PASS, installed native integration:** restricted Docker container
  used physical read-only GELLO and the PC Isaac endpoint. HOME → ready →
  following → held completed, with 586 target sends during the five-second
  following interval. This stationary-input lifecycle smoke is not operator
  direction acceptance. The actual terminal launcher also reached `needs_home`
  and exited cleanly with Ctrl+C (130).
- **M06/M14 PASS, actual watchdog:** withholding heartbeats for 0.8 s
  latched a native execution fault and preserved the executed pose. A new
  explicit owner can clear it; the GUI is left idle for operator startup.
- **Scene PASS:** eight Ubuntu OpenUSD tests cover the five static geometry
  cases plus HOME/signed/mixed poses, joint anchors, tool attachment, unchanged
  saved layers, bounded trail and relocation. The native viewport was captured
  and visually checked. Physics remains stopped; Hand-E jaws remain static open.
- **M14-A01 PASS, operator acceptance:** on 2026-09-12 the user confirmed
  successful acceptance after manual leader-to-Isaac teleoperation. This accepts
  the current arm motion/direction workflow; no additional quantitative timing
  or physical-robot result is inferred from that confirmation.
- **NOT RUN:** physical follower control,
  real-plus-sim hardware operation, active gripper animation, dynamics/contact
  and camera/MCAP recording combined with this native follower.

### Reproducible environment and evidence

Ubuntu station uses Isaac Sim 6.0.1.0, Python 3.12.3 and OpenUSD 0.26.8 in the
existing `~/venv/isaacsim-6.0.1`, with RTX 2000 Ada. The collector was installed
editable into that environment without upgrading Isaac. Added Python packages:
jsonschema 4.25.1, jsonschema-specifications 2025.9.1, referencing 0.37.0 and
rpds-py 2026.6.3; existing attrs and typing-extensions were retained.

The control-only image is `ur12e-collection:native-isaac`, linux/amd64,
`sha256:80b0409e750d2d69c2b963b581b0f8adc00f7aeaf5646a57ae0752779a82b83f`.
Its installed package was compared against the source tree. Source label
`f99acfe-native-isaac-working` explicitly denotes this uncommitted increment.
The existing production deployment was not replaced. Native checkout is
`~/ur12e-collection-sim`; scene assets are `~/ur12e-sim` and are maintained
separately from this Git repository.

Ignored evidence under that checkout's `artifacts/native/` includes
`leader-readonly.json`, `gui-control-check.json`, `leader-control-check.json`,
`watchdog-check.json`, `ready.json`, logs and `viewport.png`.
The macOS full-suite attempt initially hit five sandbox permission failures.
A permitted subset rerun passed shared-memory checks but exposed one interrupt
race in the unchanged recorder multiprocessing queue startup; retain that
failure separately from the native teleoperation acceptance. The final permitted
full suite passed **466 tests, 5 skipped**; the additional owner-isolation case
then passed in the **15-test native subset**. The intermittent recorder race
was not repaired by this increment. Full Black and Pylint checks pass; Pylint
reports 10.00/10 with intentional simulator container-flag duplication documented.

## Launch and operator handoff

Run on the Ubuntu PC. The leader must be powered, torque off and manually
supported; its unresolved elbow cable constraint still applies. Stop any other
serial reader. Start the native scene in one terminal if its window is not
already open:

```bash
cd ~/ur12e-collection-sim
~/venv/isaacsim-6.0.1/bin/python scripts/isaac_follower.py \
  --config config/teleop.isaac.json
```

In another PC terminal:

```bash
cd ~/ur12e-collection-sim
.venv/bin/python scripts/teleop.py --config config/teleop.isaac.json
```

The container runs without networking, with the selected USB device and local
IPC mount only. First Space requests speed-bounded simulated HOME; wait for
`ready`, support the leader steadily, then Space begins relative following.
Space stops and holds; another Space requests HOME for a fresh interval.
Ctrl+C stops and exits. No leader motor write or real follower control is used.
A fault requires an explicit process restart and fresh HOME/reference; input
recovery never silently resumes an active interval.

Check J2/J3 signs against the corrected calibration, all other individual axes,
and combined small motions. The leader baseline is captured per interval and
is not replaced by a median calibration HOME. The user accepted this manual arm teleoperation workflow on 2026-09-12;
this result is distinct from the synthetic trajectory tests.

## Next increment

The user selected gripper control for the next round, building on this accepted
PC-native arm workflow. Align its concrete scope and acceptance before coding:
read the leader gripper motor, map opening/closing to the simulated Hand-E, and
preserve separate command/executed-state semantics. Simulated jaw animation,
physical Hand-E actuation and leader motor writes are distinct capabilities;
this next-round intent does not authorize physical actuation. No gripper control
implementation or acceptance is claimed in this increment.


## Relative gripper extension

The separately aligned [gripper increment](gripper-teleop.md) now replaces the
static open-jaw runtime with relative 45-degree leader control. Its image identity,
protocol version and acceptance results supersede this document's arm-only
runtime snapshot. The arm-only acceptance above retains its original scope.


The user completed the combined native arm/gripper trend verification on
2026-09-12 and requested committing the implemented increment. The separate
scene project is not currently a Git repository; its deployed assets/adapter
are external dependencies and are not included in the collector commit.
