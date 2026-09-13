# M06: Real Teleoperation Edge-Case Alignment

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned control-only increment implemented; physical acceptance pending, 2026-09-13. Primary module M06; dependencies
M02-M05, M07-M11, M13 and M14. This document does not enable physical control
or authorize a hardware launch. It supplements the existing module plans.

## Evidence and scope

The operator reported successful simple mapping in the physical-drive Isaac
session. Record this as operator motion-trend acceptance only. Loaded braking,
contact fidelity, physical Hand-E actuation and real teleoperation are not
accepted by that observation.

Source inspection confirms that the native teleop configuration permits only
Isaac backends and requires recording=false. The older UR session composition
is simulation-only as well. Shared UR transport, recorder, leader mapper and
ownership components exist; a production real-arm composition is still needed.
Replacing a simulator address is not the remaining implementation scope.

No hardware was accessed in this review. No tests were run for this document.
Existing unrelated working-tree changes remain untouched.

## Reviewed behavior and proposed contracts

The recommendations below are proposals where they extend existing alignment.
An existing component is not evidence of an integrated real-device gate.

| Case | Current implementation | Proposed real behavior / remaining decision |
| --- | --- | --- |
| Startup identity and ownership | Physical factories are disabled; native config restricts endpoints | Require explicit physical profile, matching serial, validated network path, one command owner and reviewed installation. No automatic mode change, program takeover, activation or protective-stop reset. Reject mismatched image/config/protocol/calibration before acquiring control. |
| Initial HOME | Fixed branch [0,-90,-90,-90,90,0] degrees; measured arrival required | Keep this target. Validate the current pose and reviewed swept route, including long links, tool, wrist camera and cables. No arbitrary direct HOME recovery from an unknown or out-of-bounds pose. |
| Native HOME ownership | Dashboard Home exists in URSim; host loss may allow it to finish | For first physical teleop tests, recommend the explicitly bounded SDK route with controller-side watchdog. Reusing Dashboard needs a deliberate decision about host loss or a robot-side supervised program; never silently fall back between methods. |
| Starting while moving | Mapper requires stationary follower HOME and stable leader samples | Reject engagement while either input/reference is moving; preserve actual baseline, not a median. Current source window requires >=40 ms and <=2 encoder-count spread. Decide whether to extend operator settling without loosening accuracy. |
| Leader support | Native reader requires torque off; no motor writes | First real-follower tests use explicit manual support. No automatic leader HOME/HOLD is claimed. The unresolved elbow cable constraint remains; software cannot prevent operator-caused cable strain. |
| Relative reference | Fixed per-interval leader baseline; follower target is HOME plus signed delta | Preserve baseline until stop. A new interval requires HOME and a fresh reference; no clutch/rebase or resume from an arbitrary held pose in v1. |
| Slow or fast hand movement | Command conditioner limits velocity/acceleration; no explicit jerk bound | Use a separate conservative real profile. Warn on growing intent-to-command lag; stop at a configured bound instead of executing a long delayed movement after the hand stops. Add/test this guard. Jerk policy requires explicit scope; do not claim existing acceleration limiting also bounds jerk. |
| Encoder jump or restart | Range, timestamps, source epoch and sequence are checked | Add a raw acquisition jump/plausibility guard before smoothing. Test in-range jumps, encoder branch reset, reboot, malformed/missing axes and repeated data. Never smooth a reset into a valid slow move. No automatic angle wrapping. |
| Command/executed divergence | Actual limits/freshness checked; no general following-error gate | Bound both desired-to-command lag and command-to-measured lag, with explicit transient duration. Use controller speed scaling in the policy; no catch-up after a reduced/stopped speed slider. Thresholds need bench evidence before physical enablement. |
| Joint bounds | Desired, conditioned and measured joints outside limits fault; no arm clipping | Retain whole-arm stop on an invalid joint, with joint/value/reason reported. Use a reviewed smaller first-test workspace and braking margin. Do not silently clamp one arm axis while the rest continue. Gripper saturation is intentionally different. |
| Geometric hazards | Joint bounds do not certify collision-free paths | Review self/environment clearance, all moving links, Hand-E, D405 and cabling. UR installation safety settings remain a separate boundary. No claim of automatic whole-arm collision avoidance or force control. |
| Space during following | Stops and retires reference; subsequent Space requests HOME | Keep normal stop/hold and next-interval HOME semantics; never automatically return or resume. Distinguish a stop request from measured standstill. |
| Space during HOME/preparation | Busy states currently ignore Space; native engagement can cancel | Recommend Space cancel HOME/preparation as well, clear pending engagement, then hold with a new explicit HOME required. Test long press/auto-repeat, double taps and queued input across state boundaries; 250 ms debounce alone is not proof against key hold. |
| Gripper saturation | Actual start count; 512 counts/45 degrees; immutable origin; output 0..255 | Preserve relative mapping. Overtravel clips, and reversing through overtravel retains the original reference. Require actual full opening before a new baseline, not an exact POS=0 assumption on the physical gripper. |
| Object contact | Sim jaws and raw physical GET client are distinct | Contact before requested closure is a normal grasp when status supports it. Keep requested closure and measured POS/OBJ separate. A jam/fault/unknown state is not successful contact. No repeated activation or automatic force escalation. |
| Gripper on stop | Sim holds measured jaws; physical Client.hold preserves the last request without sending a stop | Recommend preserving the last bounded grasp request without opening/resetting on ordinary stop, while documenting that an unfinished close may continue. Physical freeze versus grasp-retention semantics require user alignment and testing; they are not equivalent. |
| Gripper on HOME | Native sim opens during HOME | Recommend no implicit real opening on HOME: operator explicitly releases/removes the object before the next interval; full-open readback is then an engagement prerequisite. Do not carry the simulator's auto-open behavior into physical handling silently. |
| Gripper transport | Bounded 250 ms GET/SET handling exists, physical SET not accepted | Use an independent bounded worker with coalesced setpoints; never block the 120 Hz arm loop on socket replies. Timeout, FLT or lost required readback stops arm following and invalidates the interval. Do not retry an ambiguous command and claim exactly-once execution. |
| Leader/RTDE loss | Freshness, source progression and latched faults exist | No prediction, invented samples or automatic reconnect/resume in the same interval. Short reuse uses original acquisition age. Nominal leader limit is 100 ms; native source can reject earlier after its 80 ms retained window empties. Proposed real RTDE freshness is 250 ms, not the 500 ms physics profile. |
| Process death / network loss | Orderly cleanup requests stop; SDK watchdog exists in simulator and isolated test | Verify controller-side watchdog independently of host cleanup, including frozen/killed owner and cable loss. Recovery requires a new explicit owner and reference. Host logging cannot prove successful stop when feedback is absent. |
| Protective/emergency stop or mode change | Abnormal feedback modes fault | Revoke commands, preserve diagnostics, no automatic unlock/restart/HOME. Operator restores the physical system, then repeat startup checks. Disconnect/power loss cannot guarantee physical pose or grasp retention. |
| Stop verification | Shared orderly-stop policy uses <=0.01 deg/s over 200 ms within 2 s | Retain accepted low-speed diagnostic criteria and 30 s observation, <=0.05 degree held drift. Stop dispatch is immediate; two seconds is a confirmation deadline. Fault/exit paths need independent observation too; do not equate a returned SDK call with rest. |
| Camera matching | Rejects unmatched groups; no fake frames; source faults are explicit | An isolated >16.7 ms mismatch rejects the group and records the reason. A required camera reset, stale source or overflowing queue faults recording and requests arm stop. Retain existing aggregate quality gates; do not stop for every isolated rejected group or reduce to fewer views silently. |
| Recorder/disk failure | Bounded writers, abort and atomic commitment exist | Required recorder failure stops following. Check free space/writeability before engagement. Keep failed/partial files distinguishable; no successful late commit after abort. Finalization cannot block stop or enqueue a new motion. |
| Discard / exit | Recorded session supports a; native control-only teleop does not | During recording, a stops and marks discarded; in held state it affects only the just-finished interval. Preserve files with disposition metadata. Ctrl+C stops/exits; an unfinished interval stays partial/failed. Prior committed episodes remain unchanged. |
| Real plus optional sim | Bounded optional twins exist; real composition unavailable | Real follower is authoritative; optional Isaac failure is reported and detached without stopping real recording. No automatic resync/catch-up. Require explicit readiness for a new twin ownership interval. |
| Recording provenance | Source, intent, sent command and feedback have separate contracts | Preserve leader/raw gripper, immutable reference, applied limits, command events, actual RTDE/Hand-E, source times and calibration/image identities. 120 Hz commands and 125 Hz readback remain asynchronous; do not fabricate matching samples. |

## Numerical profile to align

- First physical-test proposal: HOME and teleop command speed 1 degree/s,
  acceleration 2 degrees/s squared, with 120 Hz sending and 125 Hz receiving.
  These rates reuse the scale of the prior isolated READY test; that evidence
  does not accept six-axis servoing at the same values.
- Ordinary stop proposal: independently configured 2 degrees/s squared for
  this low-speed profile. Do not inherit the shared UR transport's current
  servoStop/stopJ 5 rad/s squared defaults. Hardware safety stops remain
  controller-owned and are not overridden by this application parameter.
- Keep jerk unclaimed until an explicit smoothing/limiting decision is made.
  Quantify raw-input jump and both tracking-error thresholds in the software
  test plan before enabling the real factory; do not copy simulator thresholds.
- Real Hand-E speed/force registers and open tolerance remain unset pending
  device-specific alignment. Simulated 50 mm/s aperture speed is not a SPE value.

## Implementation and acceptance after alignment

1. Agree the operator choices: initial rates, SDK versus native HOME, HOME-time
   Space cancellation, manual leader support, arm-limit stop, gripper stop and
   HOME opening semantics, and command-lag/jerk policy. Freeze the physical
   profile and per-joint first-test ranges separately from simulator settings.
2. Implement missing guards and shared transitions, then the explicit real
   composition. Keep UR and Hand-E I/O behind one owner and bounded adapters;
   connect the existing recorder without introducing another motion writer.
3. Test all table cases with injected source/device/recorder failures. Exercise
   physical-drive Isaac trend/lag and URSim SDK stop/watchdog separately; neither
   substitutes for real braking/contact acceptance.
4. Stage one reviewed image/config pair. On-site, verify identity/installation,
   stationary engagement, isolated joints then small combined motion, normal
   stop/HOME, unloaded gripper then contact/retention, and combined recording.
   Deliberate fault injection is a separate bounded operator-approved run.
5. Record PASS/FAIL/NOT RUN under M03-A02/A03, M04-A03, M05-A01..A03,
   M06-A01..A04, M09-A01..A04, M13-A03/A04 and M14-A02 as applicable.
   Current status of this newly proposed integrated physical matrix: NOT RUN.

## References

- [Existing physical READY/stop evidence](ready-interrupt-test.md).
- [Native gripper scope](../m14-digital-twin/gripper-teleop.md).
- [UR safety functions](https://www.universal-robots.com/manuals/EN/HTML/SW5_23/Content/prod-usr-man/complianceUR10e/H_g5_sections/safetyFunctionsAndinterfaces/configurable_functions.htm):
  controller safety limits account for stopping travel; application joint checks
  are not a replacement or proof of collision-free motion.
- [URScript watchdog reference](https://www.universal-robots.com/manuals/EN/PDF/SW5_24/scriptmanualG5/script_directory_Poly5.pdf):
  explicit violation action matters; the deployed program behavior must be
  verified rather than inferred from the host heartbeat call.

## Aligned implementation increment, 2026-09-13

The user approved the six operator choices and requested implementation, with
teleop speed changed to 2 degrees/s, acceleration retained at 2 degrees/s squared,
and no explicit jerk limiter. HOME retains 1 degree/s. Leader posture may vary
widely within the calibrated input branch; only stable acquisition and explicit
first-test relative travel bounds are required. Manual support remains mandatory.
The user additionally requires startup verification of a local wired connection
from the collection PC to the robot, following prior routed-link loss.

Implement the shared control-only teleop entry with an explicit physical adapter,
read-only preflight, local exclusive lease, bounded independent Hand-E worker,
raw-input plausibility and intent/execution lag guards, cancellable HOME, and
observed stop/exit. Preserve independent simulator configuration and optional
command twins. First physical launch is a small, empty-workspace motion/Hand-E
check with JSONL evidence; camera/MCAP session integration is a subsequent gate,
not silently claimed by this entry. Existing recording/discard contracts remain.
No physical motion is authorized for the assistant during development; provide
an operator launch command after software/simulator verification.

Current guards: configured native operating joint bounds; calibrated leader
branches unchanged; raw acquisition plausibility 180 degrees/s plus two encoder
counts; desired-to-command error <=10 degrees (operator revision below); command-to-actual error <=1 degree
with a 250 ms grace. These are configurable conservative commissioning bounds,
not physical cable limits or a guarantee of collision avoidance. Ordinary stop
uses 2 degrees/s squared. HOME arrival is 0.1 degree. No broad pose restriction
relative to leader calibration HOME is introduced. Require fresh full-open
Hand-E readback before engagement; speed/force selection is being aligned.

The host launcher and physical adapter both check the Linux route: no gateway,
Ethernet interface with carrier, same directly connected subnet, explicit source
address. A short bounded ICMP test must show no loss; cache no readiness across
launches. A passed route check is not a guarantee of subsequent network health.
Physical control requires an explicit operator launch flag and checked identity,
Remote mode, normal safety, stopped program and stationary current joints inside
the operating bounds. HOME proximity is checked before following, not at every
runtime sample. It never changes installation, mode or program selection.

## Implementation and acceptance results, 2026-09-13

Status: implemented for the control-only commissioning entry / physical
acceptance pending. On 2026-09-13 the operator explicitly approved servo-stop
deceleration of 0.1 m/s squared, now set in `config/teleop.ur.json`. Execution
continues to reject an unset value before any control connection. The operator approved Hand-E SPE=32,
FOR=32 for unloaded first testing. HOME is 1 degree/s; teleop is 2 degrees/s;
both use 2 degrees/s squared acceleration. Jerk limiting is not implemented.

The native mapping, owner and control loop are shared. `physical/` contains
explicit preflight, transport, stopping and tool responsibilities. The entry
never starts a recorded episode. Camera/MCAP integration, discard in a recording
session, real-plus-sim commissioning and loaded grasp acceptance remain separate;
the existing camera/recording functionality was not replaced.

Implemented additions:

- Direct local Ethernet route/subnet/carrier verification at the host launcher
  and again before physical SDK connection; five ICMP replies with no loss.
  No network reconfiguration or device-mode commands are sent by preflight.
- Explicit commissioning profile, operator launch flag, machine-local controller
  lease, fixed image identity and separate immutable calibration reference.
  Inputs keep broad existing calibration branches. Configured native follower
  bounds apply throughout motion; only engagement requires proximity to HOME.
  These bounds do not certify physical cable clearance.
- Raw sample plausibility, bounded intent lag, persistent executed tracking
  error and observed overspeed guards. Invalid/stale input latches a failure;
  no automatic recovery, wrapping or reference replacement occurs.
- HOME cancellation and terminal-burst coalescing. Repeated keys refresh the
  quiet timer; use distinct Space presses with >=750 ms separation. Terminal
  input has no reliable key-release events, so this is repeat suppression,
  not a physical deadman device or a certified stop input.
- Physical HOME preserves the tool. Following requires actual full-open feedback
  (POS<=5, stationary object status), then captures the relative 45-degree lever
  reference. Contact and requested/actual position stay distinct. The independent
  bounded Hand-E worker coalesces requests; stop cancels unsent pending work but
  a previously dispatched/in-flight grasp can finish. No activation, reset,
  retry or automatic opening is performed.
- Stop retires the staged gripper target so it cannot leak into the next HOME.
  Source/evidence draining remains live while the SDK stop worker owns writes.
  Exit verifies standstill, stops the SDK script, and observes actual hold for
  30 seconds. A <=1-second runtime transition to STOPPED is allowed after the
  stopScript acknowledgement while speed, drift and health remain checked.
  No protective-stop unlock, mode change, power action or automatic resumption
  is part of the physical entry.

### SDK stop correction and retained failures

The ur_rtde 1.6.5 source distribution's `scripts/rtde_control.script` handles
servoStop through `stopl`, in m/s squared. The API's tool-unit description is
therefore material: it is not interchangeable with stopJ's advertised joint
rad/s squared. Keep `servo_stop_deceleration_m_s2` separate from joint stopping.
The existing URSim transport defaults remain independent.

An exploratory verified URSim run with servoStop(0.1) and the old 5 Hz watchdog
returned false after 0.350 seconds; the simulator reported C207A0 (Fieldbus input
disconnected). This is FAIL, not successful stopping. A dedicated stop worker
now switches the controller watchdog to a two-second deadline only after
following has been revoked, executes stop, and restores 5 Hz. Normal owner
heartbeat writes are suppressed while that worker owns the SDK. No second
thread sends motion or normal heartbeat commands concurrently. Stop completion
still requires advancing actual feedback within the existing two-second gate.
This makes the stopping-phase watchdog timeout deliberately different from the
normal 200 ms watchdog; input freshness is unchanged.

The first full adapter test stopped correctly but rejected the immediate
runtime_state=0 (STOPPING) following stopScript. The bounded runtime-transition
check above fixes the readback handover without loosening stationary criteria.
Both failures remain in local `artifacts/simulator-control/` evidence.

| Acceptance slice | Result |
| --- | --- |
| M04-A03 / M06-A01,A03,A04: local source/owner/profile guards | PASS, full local suite 537 passed, 5 skipped |
| Formatting / lint | PASS, Black and Pylint 10.00/10 |
| M06-A02/A03: actual URSim physical adapter, two six-axis signed trajectories | PASS, moving peak approximately 1.87 degrees/s; stop dispatch 0.704-1.124 ms; stationary confirmation 1.082-1.381 seconds |
| M03-A02 / M06-A02: URSim HOME cancellation and exit hold | PASS, actual readback and 30-second post-script hold; no fake tool result is physical Hand-E evidence |
| Installed amd64 image on Ubuntu | PASS, 92 focused tests, networking disabled and no devices mounted |
| Physical network/read-only startup | Wired route PASS; 5/5 replies, 0% loss, maximum 0.396 ms. Execution readiness BLOCKED: POWER_OFF, Local, safety NORMAL, serial 20255100083. No RTDE control, Hand-E SET or leader motor write sent |
| Full physical teleop, controller-loss braking, grasp retention, full camera recording | NOT RUN |

Local full-suite execution initially had five macOS sandbox shared-memory errors;
a permitted rerun passed. These environment failures are retained rather than
reclassified as successful checks. The Ubuntu focused run emitted only a pytest
cache warning because its test mount was read-only; all 92 cases passed.

Passing simulator evidence:
`artifacts/simulator-control/commissioning-1789250104109611418.json`.
The reproducible simulator command is
`python scripts/sim_control.py commissioning --client-image <image>`; it checks
Docker's isolated official URSim identity and has no physical host argument.

### Delivery and operator commands

Mac and Ubuntu have the same amd64 candidate image:
`ur12e-collection:physical-teleop`, ID
`sha256:8ea4c40f0eefe2918114bd5ef8cd4729d07a2124cd6dced5c7e8edf8df84c4cd`
after the leader-reference revision below. The hold-monitor candidate was
`sha256:7fd61dee9d7f60826744239cf4e492467c02e0213726e7c937cbf03c37e1e724`. The responsiveness candidate was
`sha256:5d7b673de1c231cb73cd21a56d143d8815e56b56526f994ea27558561931306d`. The HOME/operating-bound candidate was
`sha256:c539658a2f7cd2ec2526eb679da2f8186d5551ce39181c8b2a66c7b4d64bcfd0`. The preceding candidate was
`sha256:a4d13bc7e305c495b5ed219b92230144c885e31b7da81ad737d41e4cc56fe941`.
It reuses dependency image 5185ee5 and installs only the collector wheel, without
redownloading runtime dependencies. Label `a37d75c-physical-teleop-working`
explicitly denotes uncommitted development source. The existing `current`
production image and independent Isaac environment were not replaced.
Ubuntu files are staged under `~/ur12e-real-teleop`; Python 3.12 host launcher
imports the staged source, and the restricted container runs the installed
package. Sources, calibrated configuration and launcher are mounted explicitly.

After servo-stop approval, local configuration validation passed and the mounted
PC configuration matched SHA-256
`7d9ecff98429c6dfc100dca4f4b73b6e10c6befecf7a5c5ede0185ae7d5c7348`.
No image rebuild was needed. The repeated read-only preflight passed direct
Ethernet routing, five pings (zero loss, maximum 0.304 ms), robot identity and
stationary in-bounds feedback. Dashboard reported RUNNING, NORMAL and Remote.
That preflight was BLOCKED: Hand-E returned STA=0, FLT=0, POS=3, OBJ=0,
PRE=0, COU=0, so activation is required from the operator. No activation or
other device control was sent. Later operator-started physical runs are recorded
below; the gripper was subsequently activated and engagement succeeded.

On the PC, repeat the read-only preflight after operator activation:

```sh
cd ~/ur12e-real-teleop
python3 scripts/teleop.py --config config/teleop.ur.json \
  --image ur12e-collection:physical-teleop --preflight
```

The servo-stop parameter is aligned and configured. Before control, the
operator must power/enable the arm, select Remote, verify that the
current pose and whole HOME sweep lie inside the reviewed clear workspace,
empty/open Hand-E, and manually support the powered torque-off leader. The
initial pose must be within the configured operating bounds. HOME movement
must finish before engagement, which requires stationary feedback within
0.1 degree of HOME. Do not weaken operating bounds merely to pass startup.

The operator launch, not an assistant-executed command, will be:

```sh
cd ~/ur12e-real-teleop
python3 scripts/teleop.py --config config/teleop.ur.json \
  --image ur12e-collection:physical-teleop --operator-approved
```

Space requests HOME; after ready, a distinct Space captures the baseline and
starts following. Space cancels HOME/following; Ctrl+C stops and exits after the
30-second read-only hold observation. Stopping preserves the grasp request;
returning HOME does not open fingers. The operator explicitly opens/empties the
gripper before the next interval. Evidence is under `artifacts/physical-teleop/`.

### Operator revision: intent lag, 2026-09-13

The operator reports that the movement in run `1789251218173519070` was
unintentional hand tremor and explicitly approves increasing desired-to-command
error from 2 to 10 degrees. This changes the mounted commissioning configuration
only. The existing conditioner follows the latest desired pose with the same
2 degrees/s speed and 2 degrees/s squared acceleration; it does not replay a
queue of old samples. Delayed following is allowed while engaged, but stopping
revokes it. HOME +/-5-degree joint bounds and other guards remain unchanged.
This tolerance permits following small hand movement; it does not filter tremor.

Implementation: update the configuration, validate both sides of the 10-degree
guard with the existing code, run physical control regressions, and synchronize
the mounted PC configuration without starting control. M06-A03 software checks
PASS: 31 focused physical/input tests passed locally and in the installed Ubuntu
candidate image with networking disabled and no hardware mounts. The old test
expected rejection at 0.1 radians and failed after the approved change; it was
replaced by explicit acceptance through 10 degrees and rejection at 10.01 degrees.
Formatting and diff checks passed. Local and PC configuration SHA-256 matches
`2ddaaaf0a10fa084dbbb3c599116c40a8d30544fe3191bde5b0add9c3c16dba8`.
The candidate image is unchanged; the next launch reads the revised mounted
configuration. Physical acceptance of the revised threshold is NOT RUN.

The cited run entered following, then the former 2-degree intent guard stopped
it after approximately 1.12 seconds. Standstill was confirmed approximately
0.90 seconds after the stop request. The subsequent hold observation failed on
a 0.01009 degrees/s sample against the 0.01 degrees/s limit, and its exception
masked the original error in terminal output. Full 30-second hold acceptance
is FAIL. Hold-observation robustness and primary/cleanup error reporting remain
unresolved; this configuration revision does not change either behavior.

### Separate HOME engagement from operating bounds, 2026-09-13

Aligned by the operator: HOME proximity is an engagement condition, not a
permanent travel box. Restore the existing native joint bounds in radians:
lower `[-5.5, -3.1, -3.1, -5.5, -3.1, -5.5]`, upper
`[5.5, 0.1, 0.1, 5.5, 3.1, 5.5]`. Remove the physical configuration validator's
HOME +/-5-degree restriction. These configured application bounds remain active
for desired targets, conditioned commands, actual feedback and HOME routes.
They are not collision-free workspace guarantees or manufacturer safety limits.

Reuse the existing EpisodeMapper engagement check: stationary, fresh follower
feedback within 0.1 degree of HOME, before capturing the immutable reference.
Do not add phase-dependent limit swapping. A stopped pose outside the former
5-degree box may return HOME through the same operator-started, reviewed SDK
route at 1 degree/s. Following remains 2 degrees/s, acceleration 2 degrees/s
squared, intent lag 10 degrees; all remaining guards are unchanged.

Implementation and acceptance: update config and remove the obsolete validator;
test rejection of engagement away from HOME, following beyond 5 degrees with
bounded derivatives, and rejection outside the operating bounds. Rebuild the
cached candidate wheel layer, test without devices, synchronize Mac and Ubuntu
image identities and mounted files. M06-A03/A04 local and installed-image
software checks PASS: 95 physical, input, mapping, control and native follower
tests, including the new phase/boundary cases. Black and diff checks passed;
Pylint scored 10/10 (its optional local cache write was denied). All 106
installed source files match the working tree. The dependency layer was cached;
only the collector wheel layer was rebuilt. Ubuntu installed-image verification
also passed all 95 tests with networking disabled and no hardware devices.
Mac and PC image IDs match the candidate ID in Delivery above. The mounted
configuration SHA-256 is identical on both hosts:
`d0dacd61631517a9730da7681c9d2c4dfcc14d6e355a48418afe6568c9a3ccfc`.
The staged host validator was synchronized too. Physical following under the
revised bounds is NOT RUN. No assistant control
launch is authorized by this software change.

Prior physical run `1789251501087744796` failed the former joint range check
after 2.83 seconds of following. Its stop confirmed standstill in 0.95 seconds
and completed the full 30-second hold observation (PASS for that run).
This revision supersedes all earlier HOME +/-5-degree requirements in this
document; the previous records describe historical configurations.

### Current iteration: following responsiveness (implemented, 2026-09-13)

The operator reports successful first manipulation and requests more generous
velocity/acceleration protection and more capacity for delayed following because
leader motor resistance makes small movements difficult. Run
`1789251852141615417` followed for 8.27 seconds before the 10-degree intent guard
triggered; it did not report a velocity or acceleration fault.

Operator explicitly approved these values on 2026-09-13: following speed 5 degrees/s,
acceleration 5 degrees/s squared, intent error 30 degrees, and measured-speed
guard 6 degrees/s (same 20 percent margin). Retain HOME speed/acceleration,
stopping decelerations, joint bounds, tracking and freshness guards. Keep the
existing latest-target conditioner; no queued trajectory replay or extra filter
layer. At its 90-percent speed headroom, a fixed 30-degree gap takes more than
6.7 seconds to close including acceleration/deceleration. New input replaces the
desired target; Space or Ctrl+C revokes remaining following immediately.

Implementation: update the physical profile and configuration together, test
derivatives, larger intent lag and stop revocation, rebuild the cached wheel
layer and verify identical PC deployment. M06-A03 software and physical tests
for these revised values PASS as recorded below. Physical acceptance is NOT RUN.

Software results: 96 focused tests passed locally and in the rebuilt amd64
candidate without device mounts or networking. These cover a 30-degree target
with bounded derivatives, the 30-degree intent guard boundary, unchanged HOME
settings, and existing stop revocation. Pylint 10/10, Black and diff checks PASS;
all 106 installed source files match the working tree. The cached dependency
layer was reused. Physical motion and 30-second hold at the revised speed are
NOT RUN; the existing hold-observation and error-masking issues remain open.
This aligned revision supersedes the earlier 2 degrees/s, 2 degrees/s squared,
10-degree intent gap and 2.4 degrees/s measured-speed settings for following.

Deployment PASS: the Ubuntu installed candidate passed the same 96 tests with
networking disabled and no devices. Mac and PC image IDs match the current
Delivery ID. The mounted configuration SHA-256 matches on both hosts:
`d2dc008155078c9483cf1c91c0432ee94dc235eb09df82d0514e9af4039d7d6e`.
The staged host validator is updated. Relaunch is operator-only using the
existing command; no real-device control was sent during this update.

### Hold monitoring tolerance (aligned, 2026-09-13)

The operator authorizes selecting a minimal correction for oversensitive hold
monitoring. Use 0.05 degrees/s for already-held motion monitoring in both READY /
held states and the 30-second post-stop observer. Keep the 0.05-degree drift
bound, health/runtime/freshness checks, and the 0.01-degree/s arrival/engagement
and 200-ms stop-confirmation criteria unchanged. Use one shared HOLD_SPEED
constant; do not add timing windows or alter the conditioner. Run
`1789252230884814549` failed while READY, with an adjacent elbow feedback sample
of 0.0106 degrees/s and recorded drift only 0.0047 degrees.

M06-A03 acceptance: test both monitoring paths with small speed noise, rejection
above 0.05 degrees/s, independent drift rejection, and retention of strict stop
confirmation. Software checks and deployment are pending; physical acceptance is
NOT RUN. Error-reporting cleanup remains separate. No real control is launched.

Local and installed amd64 software validation PASS: 109 focused tests, Pylint
10/10, and diff checks. All 106 installed source files match the working tree.
A partially applied development edit initially omitted HOLD_SPEED and failed the
12 new monitoring cases; adding the shared constant resolved all failures before
build or deployment. Runtime changes are one constant and two references.
Ubuntu deployment PASS: the installed candidate passed all 109 tests with no
network or hardware access. Mac and PC image IDs match the current Delivery ID;
staged host sources are synchronized. Configuration is unchanged. Physical
acceptance awaits the operator launch; no device control was sent.

### Leader startup reference tolerance (aligned, 2026-09-13)

The operator requests increasing the reference-window peak-to-peak allowance
from 2 to 10 encoder counts (0.87890625 degrees at 4096 counts/revolution).
Apply this to each of the seven leader channels, including the gripper. Preserve
freshness, continuity, minimum 40-ms span, follower stationary HOME checks and
all running guards. The last genuine sample remains the immutable baseline;
do not average or change the relative mapping. A spread greater than 10 still
rejects engagement. This is separate from the running raw-jump allowance.

M06-A03/A04: test exact 10-count acceptance and 11-count rejection independently
on every channel, and verify that an accepted noisy baseline starts at HOME.
Rebuild the cached wheel layer and synchronize the candidate to PC after tests.
Software acceptance and deployment are pending; physical acceptance is NOT RUN.
No real device control is sent by the update.

Local and installed-image software checks PASS: 115 focused tests, including
seven-channel 10-count acceptance / 11-count rejection and last-sample reference
retention. Black, Pylint (10/10), and diff checks passed. All 106 installed source
files match the working tree. Dependencies were reused; only the collector wheel
layer was rebuilt. Ubuntu deployment PASS: 115 installed-image tests passed with no network or
hardware access. Mac and PC candidate IDs match the Delivery ID; the staged
host source is synchronized. Physical acceptance remains NOT RUN.

### First physical teleoperation loop accepted, 2026-09-13

The operator reports the final run completed successfully. Read-only log review
confirms the control-only loop on candidate
`sha256:8ea4c40f0eefe2918114bd5ef8cd4729d07a2124cd6dced5c7e8edf8df84c4cd`.
Both reviewed runs used 5 degrees/s, 5 degrees/s squared, 30-degree intent lag,
6 degrees/s measured-speed guard, 0.05 degrees/s held monitoring and the 10-count
leader startup reference window. The assistant issued no control during review.

- Prior effective run `1789252823109496901`: following lasted 117.60 seconds
  before `leader outran command; stop and reinitialize`. The final recorded base
  desired/command gap was 29.91 degrees. The rejected sample is not logged, so
  base is the likely triggering axis, not a conclusively recorded fault axis.
  Actual speed peaked at 5.91 degrees/s, below the 6-degree/s guard but above the
  nominal 5-degree/s command limit; commanded derivatives and actual servo
  response are distinct. Stop was dispatched in 12.09 ms and standstill confirmed
  in 1.29 seconds. Only 18.20 seconds of post-stop hold evidence exists, with no
  `observation_complete`. Recorded hold speed peaked at 0.0191 degrees/s and
  drift at 0.00479 degree; those samples do not explain the truncated observation.
  Its termination cause is unresolved; do not label it a hold-threshold failure
  or a complete 30-second acceptance.
- Intervening run `1789252984448987444` contains configuration only. It provides
  no following evidence and is excluded from the two effective-run comparison.
- Successful run `1789252989310631297`: HOME completed in 22.86 seconds, then
  following ran for 84.98 seconds with no fault event. Command cadence averaged
  120.00 Hz; this is not a worst-case timing or RTDE-rate guarantee. Largest
  recorded intent gap was 22.86 degrees; actual speed peaked at 4.93 degrees/s.
  Space requested servo stop, dispatched after 16.62 ms, and the owner entered
  held after 216.44 ms. The arm was already stationary in the final pre-stop
  sample, so this is not a maximum-speed braking test. Ctrl+C followed after
  12.37 seconds of held state, and the full 30-second observer completed.
  Observed hold speed peaked at 0.0270 degrees/s and drift at 0.00469 degree.
  Hand-E actual POS spanned 3..185, requested PRE 0..186, with FLT=0 throughout
  following. This establishes real gripper variation, not full closure or loaded
  grasp acceptance. The previous run reached POS=214, also short of full range.

Acceptance: the first real leader -> UR + Hand-E control-only loop is PASS,
covering HOME, relative engagement, bounded following, Space hold and Ctrl+C
observed exit. M06-A03/A04 receive scoped physical evidence; the complete module
remains acceptance pending. No camera/MCAP recording, real-plus-sim execution,
leader powered HOME, full gripper endpoints/contact, injected communication
faults, or maximum-speed stopping acceptance is established by this run.

Keep the accepted operating parameters unchanged. Follow-up polish: record the
rejected input / joint / value and stop cause before cleanup; preserve primary
and cleanup errors; report an interrupted observation distinctly. Separately
consider recoverable startup-reference rejection rather than ending the session.
These follow-ups are not implemented or deployed by this review. Preserve the
30-degree lag boundary until a distinct change is aligned; additional filtering
or further lag tolerance is not needed to declare this first-loop result.

Evidence copies are kept outside version control under
`artifacts/physical-teleop-review/20260913/<run-id>.jsonl`; original logs remain in
`~/ur12e-real-teleop/artifacts/physical-teleop/<run-id>/trace.jsonl` on the PC.

### Handover rejection diagnosis and next speed proposal, 2026-09-13

The operator supplied the terminal error for configuration-only run
`1789252984448987444`: `robot moved during control handover`. This occurs after
read-only stationary preflight and the SDK idle control-script upload, before
HOME or following commands. The check conflates three predicates: mode tuple
not `(robot=7, safety=1, runtime=2)`, joint displacement from pre-upload feedback
above 0.1 degree, or any single speed sample above 0.01 degrees/s. The recent
HOLD_SPEED change does not affect this handover speed threshold. Before/after
feedback is not emitted, so the failed predicate cannot be recovered. Single-frame
speed noise and delayed runtime transition are plausible, not established causes;
actual displacement cannot be excluded from this log. The next run succeeding
about five seconds later is consistent with a transient, but proves no cause.

Proposed correction (not implemented): emit both snapshots and individual failed
predicates; handle normal script-start runtime transition with bounded waiting
for fresh feedback, keeping robot/safety faults distinct and retaining drift
protection. Do not solve ambiguous handover rejection solely by widening speed.

Proposed next operator test (not deployed): following 8 degrees/s, acceleration
10 degrees/s squared, measured-speed guard 9.6 degrees/s; keep HOME 1 degree/s
and 2 degrees/s squared, 30-degree intent gap, existing joint/tracking/freshness
bounds and stop decelerations. This is a test candidate, not a validated safe
operating speed. The previous 5-degree/s configuration remains deployed.
Higher speed must separately verify an in-motion stop against the existing
2-second confirmation and 30-second hold gates; prior successful Space stop
occurred after motion was already stationary. Do not extend the stopping gate
without reviewing the resulting measured behavior.

UR's official servoJ documentation states that its `a` and `v` arguments are
unused, and warns that high gain / short lookahead can cause instability with
noisy targets. The project already supplies zero for those arguments and limits
trajectory derivatives in the host conditioner. Retain lookahead=0.1 seconds
and gain=300 for the proposed test; tune host limits, not those servo parameters.
Source: https://www.universal-robots.com/manuals/EN/HTML/SW5_20/Content/prod-scriptmanual/G5/servoj_qavt0-008lookahead_time.htm

### Handover diagnostics and bounded transition (aligned, 2026-09-13)

The operator approved concise diagnostic output and bounded waiting for SDK
program startup. Record pre-upload feedback and each checked post-upload sample,
with an explicit accepted/waiting/rejected outcome and reason. Permit up to one
second for runtime 0/1 to become running (2), with fresh progressing feedback.
Reject unhealthy robot/safety modes, 0.1-degree position displacement, speed
above the unchanged 0.01-degree/s threshold, timestamp regression, and feedback
stagnation beyond 250 ms. Waiting never sends motion, changes mode, or retries a
failed controller connection. Print one waiting message and an outcome summary
with mode tuple, maximum position change and measured speed.

Acceptance: fake-receiver tests cover delayed startup success, timeout, stale
feedback, unhealthy modes, position/speed violations, and original/final evidence.
Run the software suite and preserve existing real-loop acceptance separately.
No 8 degrees/s proposal is approved; the tested 5 degrees/s profile remains.

Handover software acceptance PASS: seven deterministic startup scenarios cover
normal transition, timeout, stale feedback, timestamp regression, unhealthy mode,
position displacement and small speed violation, including trace fields and
terminal outcome text. Full local software suite: 573 PASS / 5 environment skips.
The first restricted run had five shared-memory permission failures; the suite
passed with required local shared-memory permission, without hardware control.
Black checked 188 files; project Pylint scored 10/10. Manual credential-pattern
review found no embedded secrets in the added physical adapter/configuration.
Station IP, serial and device path are intentional deployment identity fields.

The handover diagnostic increment is software-verified only. No new physical
handover run or image rebuild was performed for this commit batch; the deployed
candidate remains the previously accepted `8ea4c40f...` image. A later build must
carry the new committed diagnostics before collecting additional handover data.
Earlier descriptions of a proposed handover fix are superseded by this section;
primary-versus-cleanup exception preservation and recoverable leader engagement
remain unimplemented. Current movement parameters are unchanged.

### Post-acceptance teleop adjustments (aligned, 2026-09-13)

The operator approves the previously proposed 8 degrees/s following speed,
10 degrees/s squared acceleration and corresponding 9.6 degrees/s observed-speed
guard. SDK HOME becomes 3 degrees/s and 6 degrees/s squared. Stop decelerations
remain unchanged. Additional physical stopping/fault/contact tests are deferred
by the operator; mark them NOT RUN rather than infer coverage from the emergency
stop button. Existing software protections remain active.

A leader startup reference whose spread exceeds 10 counts is a recoverable
engagement condition: remain in a waiting-for-leader state, retry on fresh input,
and report the reason once. Keep the follower held at HOME; never start following
or recording until a genuine stable reference passes. Space may cancel this
pending start and Ctrl+C exits. Other invalid/stale/failed inputs remain faults.
Use a typed transient exception, not matching arbitrary error strings.

Run static and behavioral regressions and commit these adjustments before
recording integration. Physical acceptance at these new rates is NOT RUN.
The operator supplied a 127-mm TCP translation; local-axis and active-controller
configuration confirmation is pending and must not be invented.

Teleop adjustment software results: 124 focused tests PASS, Black PASS, Pylint
10/10. Tests retain unchanged stopping deceleration, enforce the revised profile,
verify one retry message for repeated unstable windows and preserve fatal stale
input behavior. This increment has not yet been deployed or physically tested.

The `8e34182` adjustment and prior handover diagnostics are now included in the
`a4ac32d` physical recording image on Mac and Ubuntu. See the
[M09 delivery record](../m09-session/physical-recording.md#image-delivery-and-pc-checks-2026-09-13).
New-rate physical movement acceptance remains NOT RUN; deployment is software
and camera-only verified. The operator will initiate the next combined run.
