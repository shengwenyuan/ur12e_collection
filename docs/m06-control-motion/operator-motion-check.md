# M06: Operator-Started Physical Motion Checks

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: draft procedure; physical motion NOT RUN.
Primary module: M06. Related acceptance: M03-A01/A02, M06-A02/A03/A04.

## Authorization and scope

On 2026-09-11 the user requested physical arm verification with expected behavior
explained before each step. The operator owns program preparation, start and
abort. The assistant may receive state only: no RTDEControl/IO, URScript send,
Dashboard load/play/stop, mode change, gripper command or physical motion backend
enablement. The exact first test below is proposed for alignment, not executed.
Keep the physical backend disabled and the real installation unchanged.

## First test: one-degree wrist3 excursion

Prerequisites: stationary near the agreed READY; Manual/Local and stopped
program; operator confirms clearance for the gripper, camera, brackets and cables
through the complete one-degree excursion. Existing 5 kg/zero-CoG values remain
site configuration, not an independently verified tool model. The operator must
confirm that the configuration remains applicable before movement. The active
TCP is the flange frame; use joint-angle waypoints, not Cartesian jogging.
Gripper remains open and unchanged. No simultaneous camera or gripper test.

Prepare a separate, non-looping PolyScope program using the current installation.
Use native MoveJ with explicit speed/acceleration controls (not OptiMove percentage
controls), joint speed 1 deg/s (0.0174533 rad/s), acceleration 2 deg/s²
(0.0349066 rad/s²), blend zero. Capture current actual joints as A without moving.
Copy them into B and change only wrist3 by +1 degree, preserving angle branches.
The expected A is approximately `[0,-90,-90,-90,90,0]` degrees.

Program sequence: A -> B -> wait 3 seconds -> A -> wait 3 seconds -> finish.
All waypoints use the same explicit low motion parameters; do not inherit the
60/80 native Home defaults or the SDK defaults. Do not add Home, gripper,
External Control, before-start motion or an infinite loop. Do not overwrite a
working site program/installation. If PolyScope requests a separate AutoMove to
the start position, stop and review the mismatch rather than assuming this
pre-start movement uses the test's MoveJ settings.

After setup and alignment, start a bounded receive-only monitor and confirm its
ready state before the operator presses Play. Maintain the existing Manual
enabling behavior and do not switch to Remote/Automatic. The operator owns the
pendant stop and emergency stop if needed; the monitor cannot stop the robot.
If monitoring fails, report it promptly and invalidate dependent acceptance;
network delivery cannot guarantee real-time operator notification.

## Expected observations and acceptance

These are proposed diagnostic criteria, not controller safety limits.

| Case | Proposed criterion | Current result |
| --- | --- | --- |
| M03-A01 / M06-A03, first motion observation | Actual wrist3 rises by 1 degree and returns; other joints remain within 0.1 degree of A; observed peak joint speed no greater than 1.2 deg/s | NOT RUN |
| M06-A02, UR-only numerical return | Within 0.1 degree of A after return; last 3-second hold has max joint speed below 0.01 rad/s and joint span below 0.05 degree | NOT RUN |
| M06-A04, start/route check | Correct captured A, angle branches, program settings and operator-confirmed clearance | NOT RUN |
| M03-A02, interruption during motion | Separate subsequent test; this first endpoint-stop test cannot establish interruption behavior | NOT RUN |

At unscaled 1 deg/s and 2 deg/s², each one-degree leg is approximately 1.5 s
under a trapezoidal profile; scaling can make it slower. This is a planning
estimate, not a deadline. Do not increase speed to meet a duration expectation.
Record actual q/qd, TCP, runtime/safety state, source and receipt clocks, and
speed-scaling outputs where available. Preserve source gaps; repeated/stale
samples cannot establish an upper bound on unobserved peak speed or stopping time.
Observed overspeed, wrong direction/joint, abnormal vibration/noise, unexpected
clearance or safety status requires operator abort and investigation. Never
automatically return after an abort. No application servo, teleoperation,
controller-watchdog, full-arm Home route or GELLO acceptance follows from this test.

Reference: [UR Move parameters and joint-angle waypoints](https://www.universal-robots.com/manuals/EN/HTML/SW5_19/Content/prod-usr-man/software/PolyScope/content/BasicProgNodes/commandtab_move_pane_en.htm).

## Operator-started +5-degree observation (2026-09-11)

The user changed wrist3 excursion to +5 degrees, expected approximately five
seconds of movement, and required at least 30 seconds of supervision. The
assistant started a 60-second RTDE output-only monitor, confirmed readiness,
and never sent a physical control command. The operator subsequently reported
several visible cycles with only wrist3 moving. The operator's looping program
behavior differs from the original one-shot draft; do not silently treat it as
execution of that draft or its low-speed settings.

First observed wrist3 was already +5.001 degrees with a stopped program. Its
preceding approach is outside the captured interval. The complete monitor
captured 5,866 diagnostic reads over 59.999 seconds, then disconnected normally.
No collector container remained running. Receive rate was 125 Hz; host getters
were sampled approximately every 10 ms, not an atomic packet logger.

| Case | Actual result |
| --- | --- |
| M03-A01 motion readback | PASS for observed movement: wrist3 range -0.00395 to +5.00201 degrees; eight full 0->5->0 cycles in the main looping phase, followed by another ascent |
| Uncommanded-joint observation | Other five joint spans <=0.007942 degrees; consistent with the operator's wrist3-only report |
| M06-A03 proposed low-speed criterion | FAIL: actual wrist3 peak 20.0816 deg/s (0.35049 rad/s), target output peak 19.8864 deg/s; exceeds the proposed 1 deg/s setting and 1.2 deg/s diagnostic threshold |
| Expected duration/dwell | Main-loop endpoint arrivals were approximately 0.5 s apart, about one second per round trip; the proposed five-second one-way expectation and three-second dwells were not observed |
| M06-A02 final return | NOT PASSED: final wrist3 +4.89968 degrees, runtime state 4 (paused), not returned to A/READY |
| Static post-pause observation | Last three seconds: peak joint speed 0.001239 deg/s, max joint span 0.006188 degrees; observed stationary state only |
| M03-A02 deliberate interruption timing | NOT RUN as a controlled acceptance: pause/stop transitions were observed but the operator-button timestamp was not recorded |
| Health | Robot mode 7 and safety mode 1 throughout; runtime states {0,1,2,3,4} observed |

There were 113 repeated source timestamps, zero backwards timestamps, maximum
source jump 96 ms and maximum host read interval 10.654 ms. Three additional
getter groups crossed a controller update. Preserve those limits; sampled peaks
are not guaranteed upper bounds between samples. This does not resolve the
previous intermittent network behavior or establish servo timing acceptance.

The assistant notified the operator of the speed mismatch as soon as the
completed trace was analyzed and requested keeping the program paused. No stop,
return or restart command was sent. Next operator check: inspect the actual
MoveJ speed and acceleration, per-waypoint overrides, blend, wait nodes and loop
settings. Do not assume the old Home defaults or speed slider are the cause
without inspecting the program. Before another run, confirm explicit 1 deg/s,
2 deg/s², zero blend and one-shot sequencing; obtain actual program values and
start a fresh bounded monitor first. Do not automatically move from +4.9 degrees
back to READY while preparing that check.

Evidence: local `artifacts/ur-wrist5-20260911/` contains monitor, raw JSONL,
identity, log, summary and offline summarizer; remote raw evidence is under
`/home/robot2026fall/ur-wrist5-20260911/`. Runtime image `a3d22d1ffa6c`.
Production code, physical backend authorization and station configuration remain
unchanged. Physical low-speed movement is not accepted by this run.

### Operator identifies percentage-based settings

The operator reports that speed was not changed before the run and that both
speed and acceleration are shown as percentages. This is consistent with
OptiMove; the selected Motion Controls value and actual percentages have not
been read back. Do not convert an arbitrary percentage into deg/s or deg/s².
The official PolyScope 5.22 manual documents a Motion Controls selector and
Classic mode with explicit Joint Speed and Joint Acceleration units.
For the next proposed run, the operator should select the parent MoveJ node,
choose Classic, set 1 deg/s and 2 deg/s², and verify waypoint overrides, zero
blend, three-second waits and one-shot sequencing. No program resume/start is
part of this configuration check. Because the last observed pose is near +4.9
degrees, start-position/AutoMove handling must be checked before executing any
return to zero. The assistant remains receive-only and will announce monitor
readiness before the operator starts; monitoring must last at least 30 seconds.

Reference: [UR PolyScope 5.22 Move controls, page 126](https://www.universal-robots.com/manuals/EN/PDF/SW5_22/user-manual-UR10e-PDF_online/711-039-00_UR10e_User_Manual_en_Global.pdf).

## Partial Classic-speed correction: 60-second recheck

The user reported the settings changed and requested monitoring. A fresh
60-second receive-only monitor captured the initial wrist3 near zero before
announcing readiness. It completed normally with 5,866 samples over 60.000 s;
no physical control commands were sent and no container remained running.

Two full outward legs changed wrist3 from approximately 0 to 5 degrees over
5.45 s and 5.42 s, with observed peak speeds 1.0987 and 1.1048 deg/s: PASS for
these legs against the proposed 1.2 deg/s diagnostic threshold. Both return
legs remained fast: approximately 0.50 s each with observed peaks 20.1081 and
20.0669 deg/s. The program repeated without the proposed endpoint dwells.
A third outward leg was interrupted near +0.62 degrees; final runtime was paused.
The assistant reported the asymmetric speeds during the monitor and requested
that the operator keep it paused. This report did not issue a robot stop.

Overall low-speed round-trip acceptance remains FAIL. The intended non-looping
sequence and dwell times also did not pass. Final wrist3 was +0.62333 degrees,
so the requested return to A/READY was not completed. The other five joints had
maximum position span 0.007493 degrees. Last three seconds after pause showed
maximum joint speed 0.001352 deg/s and span 0.005574 degrees. All observed robot
and safety modes remained 7 and 1. This is observed pause stability, not a timed
stop-command acceptance; no pendant-button timestamp was collected.

There were 43 repeated source timestamps, no backwards timestamps, maximum
source interval 40 ms, maximum host read interval 10.622 ms and two extra-getter
update crossings. Sampled peaks do not bound unobserved intervals.

Next operator verification: inspect every outbound AND return MoveJ and any
waypoint-specific overrides; all must use Classic 1 deg/s, 2 deg/s², zero blend.
Disable repetition and add explicit three-second endpoint waits. The asymmetric
observations suggest a remaining per-leg/per-waypoint configuration difference,
but the actual program has not been inspected and the cause is not yet proven.
Do not resume just because the outbound leg is now slow. Start a fresh monitor
before any subsequently aligned run; no automatic return to A is authorized.

Evidence: local `artifacts/ur-wrist5-classic-20260911/` and remote
`/home/robot2026fall/ur-wrist5-classic-20260911/`; image `a3d22d1ffa6c`.

### Operator acceptance and scope clarification

The operator states that no return leg was intentionally designed, believes the
controller handled the return, and accepts the observed demonstration. Record
that operator acceptance without rewriting the measured result or inferring how
the return was triggered. The actual program structure and return source remain
unverified.

Accepted evidence from this run: physical wrist3-only motion readback (M03-A01),
two approximately 5-degree low-speed outward legs meeting the proposed observed
speed threshold, and stable joint posture after operator pause. This is a basic
operator-driven movement demonstration. It is not full M06 acceptance.

The earlier whole-round-trip low-speed criterion remains a measured FAIL, with
approximately 20 deg/s return peaks; the user accepts the demonstration despite
that result. Keep return-generation/source, return speed and deliberate final
READY arrival unresolved. Native controller generation alone does not establish
compliance with the project's chosen limits. No application-controlled motion,
teleoperation, timed-stop, watchdog or automatic-return acceptance follows.
The assistant remains prohibited from sending physical control signals.

## Operator-launched timed SIGINT test proposal (2026-09-11)

Status: awaiting identification of the operator's motion source; no test launched.
The user requests a script they will start over SSH, with logged independent
supervision, an automatic SIGINT after two seconds, and subsequent offline review.
The operator will provide motion during that interval and expects SIGINT to end
the motion. The assistant does not launch the physical stop-capable process.

SIGINT is a host process signal. The existing observation recorder has no robot
stop authority, and the physical control factory remains disabled. Consequently,
killing that recorder cannot establish robot stopping. An operator-launched test
must explicitly connect its SIGINT handling to the stop interface appropriate
to the actual motion owner. Do not enable the mainline physical backend merely
to make this diagnostic possible.

Proposed test structure:

1. Establish matching controller identity and an independent output-only logger;
   fail preflight if feedback is unavailable. Keep motion start with the operator.
2. Define and print an explicit armed timestamp after setup. The proposed two-second
   timer starts there, excluding SSH/Docker/SDK initialization. This timer origin
   must be communicated in the final operator instructions.
3. Signal only the test owner with SIGINT after two seconds. Record signal send,
   handler entry, stop request and response timestamps separately. Do not terminate
   the independent observer with that signal.
4. Continue observation for at least 30 seconds after the signal; flush timestamped
   logs throughout. Report motion before interruption, feedback continuity, time
   to observed rest, final runtime/safety state and post-stop drift. Missing motion
   or stale feedback makes the stop measurement inconclusive.
5. This checks orderly SIGINT handling only. It does not establish behavior after
   SIGKILL, host failure, network loss or a safety-rated emergency stop.

For a native PolyScope program, the documented Dashboard `stop` operation applies
to program execution and is marked Remote-Control-only. It is not established
as a stop for pendant Move-page jogging. The latest observed controller mode is
Local. Do not change mode or substitute URScript/RTDEControl to bypass a failed
preflight. Resolve the operator's motion source before selecting the stop path
or distributing a runnable physical stop test.

Reference: [UR Dashboard stop and Remote Control requirements](https://www.universal-robots.com/manuals/EN/HTML/SW5_23/Content/prod-dashboard/Dashboard_table.htm).

## Revised supervised-test ownership (2026-09-11)

This decision supersedes the preceding operator-launched test proposal and its
unresolved operator motion-source question. The user now assigns the assistant
ownership of remote test execution, motion control, interrupt injection and
logged observation, conditional on explicit operator permission before each
physical launch. Agreement with this workflow is not permission to start a run.
The operator must be beside the physical emergency-stop control. No physical
control connection, program upload/start or motion is authorized by this
planning exchange alone. The existing physical backend stays disabled.

Prepare and validate the harness offline or in URSim first. Before requesting
physical launch permission, present the exact initial pose and target, motion
interface, speed/acceleration, stopping parameters, interruption timing and
expected outcome. Confirm the operator's presence and route clearance as part of
that specific permission. Do not reuse an earlier permission for another run,
restart or different movement. Do not automatically return to READY afterward.

The first proposed physical test is orderly SIGINT handling during a bounded
single-joint move, using the previously exercised wrist3 excursion as a candidate.
The exact physical motion parameters and harness are not yet approved or tested.
Inject SIGINT into the motion owner two seconds after the declared motion-start
event; record any dispatch delay. That owner's explicit stop path must end its
own motion. A separate output-only observer survives SIGINT, flushes timestamped
logs and observes at least 30 seconds after interruption. The assistant then
reviews actual motion, stop timing and sustained hold; it need not provide live
chat supervision. Logs are evidence, not an emergency-stop mechanism.

Orderly SIGINT, process kill, network loss and input/source failure remain
separate acceptance cases. Do not claim whole-system fault acceptance from a
standalone motion-stop harness or infer a safety-rated stop from application
cleanup. This exchange launches none of those tests.

The user's subsequent decision replaces the candidate single-joint excursion
with a return toward the established READY from the current operator-declared
safe pose. Code development is explicitly authorized before physical launch.
The concrete parameters, implementation, simulator acceptance and staged lab
test are recorded in [READY interruption test](ready-interrupt-test.md).
That plan supersedes the preceding test draft; physical launch still requires
the operator's explicit signal after Remote Control selection.

After that explicit launch signal, the first READY-directed SDK/SIGINT physical
test ran once. The stop path and subsequent stable intermediate-pose hold were
observed, but strict overall acceptance FAILED on the <=1-second first-rest gate
and the <=0.01-degree/s hold gate beginning at the first low-speed crossing.
See the [physical result and settling-tail analysis](ready-interrupt-test.md).
No retry or continuation to READY occurred.
