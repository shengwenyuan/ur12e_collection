# M05: Read-Only Hand-E Feedback

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / physical persistent-read acceptance pending.
The user approved GET-only integration, explicitly forbidding control signals.
Scope, implementation steps and acceptance are in the
[shared integration plan](../m13-acceptance/readonly-integration.md).

Use the existing verified bridge endpoint from station configuration; preserve
POS/PRE/STA/OBJ/FLT/COU raw values and each non-atomic polling interval. No SET,
activation, calibration, reset, release or reconnect is implemented. A deadline
covers the whole poll; malformed, oversized or stalled replies close the reader.
The physical preflight received legal replies while STA was zero. Active-device
freshness, firmware and identity are not inferred from that result.

M05-A01/A02 software/readback slices pass. Persistent physical integration and
M05-A03 grasp retention under actual control remain NOT RUN; no control code was
added. The raw protocol, output-only interfaces, late/failing sources and MCAP
verification are covered by the shared offline tests.


2026-09-10 simulator audit: keep the approved Hand-E bypass. Every simulated
controlled episode records the bypass and null gripper values. No URCap SET,
activation or inferred gripper state was added. Unit tests preserve raw readback
and reject fabricated values in bypassed recordings. Physical URCap actuation,
reconnection ownership and grip retention require the actual device/protocol
acceptance; simulating an invented TCP actuator would not validate them.

## Powered-station bridge recheck (2026-09-11)

The user confirmed that Hand-E is mounted and asked about its absence from TCP
Visualization and previous direct access. The assistant verified controller
serial `20255100083`, then used only the existing Reader's six GET requests at
`10.18.1.106:63352`. Three polls returned identical raw values:
`POS=3, PRE=0, STA=0, OBJ=0, FLT=0, COU=0`, taking 22.1-25.9 ms each.
PASS for bounded bridge readback; active-device readiness/freshness and all
actuation acceptance remain NOT RUN. STA zero is consistent with reset/not
activated status; no activation or reset was sent to change it. FLT zero alone
is not proof of operational readiness.

TCP configuration defines a tool-frame transform, independently of bridge
reachability or displayed gripper geometry. The user has not yet supplied the
six active TCP offset values. The reported 5 kg/zero-CoG installation values
remain unverified against the complete physical tool assembly.
Next operator step: inspect the Robotiq URCap installation device/status page
and the active TCP numeric fields, without activation or open/close commands.
Activation can move the fingers and requires a separately aligned operator test.
See the [UR TCP definition](https://www.universal-robots.com/manuals/EN/HTML/SW5_24/Content/prod-usr-man/software/PolyScope/content/installation_g5/installation_TCP_configuration_en.htm)
and [Robotiq status and activation definitions](https://assets.robotiq.com/website-assets/support_documents/document/online/Hand-E_Instruction_Manual_Web_20190122.zip/Hand-E_Instruction_Manual_Web/Content/4.%20Control.htm).

Evidence: local `artifacts/hande-readonly-20260911/` and remote
`/home/robot2026fall/hande-readonly-20260911/`, containing the exact script and
report. Current immutable image `a3d22d1ffa6c`; no control interface, program,
mode, payload, TCP, gripper state or production configuration was changed.

### Operator inspection confirmation (2026-09-11)

The operator confirms that the Robotiq URCap recognizes Hand-E as ID 1 and that
its fingers are currently open. This is operator-reported device recognition
and physical posture, separate from the bridge's previous STA=0 observation.
Do not infer activation readiness from an open posture or map URCap ID 1 to a
Modbus slave address without verification. The discrepancy requires a live
operator-action/readback comparison before declaring active feedback accepted.

Proposed next check, not yet run: keep UR joints stationary while the operator
uses the Robotiq toolbar for a low-speed, low-force empty close/open cycle;
the assistant records GET-only feedback and UR actual joint state. Align the
step and start the bounded reader before asking the operator to act. If the
UI requires activation, stop to align that distinct finger-motion step first.
No assistant-issued SET, activation or arm command is authorized.

## Operator-driven position/speed/force observation (2026-09-11)

The user explicitly authorized a receive-only monitor while operating the
Adaptive Gripper toolbar to vary position, speed and force. A diagnostic script
outside mainline used a fixed GET-only list: POS/PRE/STA/OBJ/FLT/COU plus
SPE/FOR/ACT/GTO. Those four extra fields are diagnostic observations, not a
change to the production schema or Reader. A separate RTDEReceive thread
recorded actual UR joint state. No assistant-issued control, activation, stop,
reset, SET, input-register write, program or mode command was sent.

The requested 90-second monitor ended early after approximately 65 seconds:
one gripper reply exceeded the shared 250 ms poll deadline. Both reader threads
closed; the diagnostic container exited with failure and no automatic reconnect.
Complete polls span 64.520 s: 645 gripper polls and 1,934 UR observations.
Preserve this as an incomplete diagnostic, not a successful full-duration run.

| Case | Observed result |
| --- | --- |
| M05-A01 active bridge observation | PASS for observed interval: ACT=1 and STA=3 throughout; all ten GET fields returned numeric values |
| Position readback | POS ranged 3-249 with 131 changes; PRE ranged 0-255 with 44 changes; no external precise position measurement or automated target-tracking acceptance |
| Speed setting readback | SPE ranged 0-255 with 36 changes; raw setting echo, not independently measured finger velocity |
| Force setting readback | FOR ranged 0-255 with 52 changes; raw setting, not measured force or grasp-force calibration |
| Other raw observations | OBJ in {0,3}, COU 0-23, GTO in {0,1}; no object-retention acceptance inferred |
| Fault-free/full-duration monitoring | FAIL: FLT changed from 0 to 4 at 59.715 s and persisted for 49 complete polls; a subsequent GET timed out |
| Stationary UR observation | Maximum absolute joint speed 0.000133277 rad/s; maximum joint position span 0.007124 degrees; robot mode 7, safety mode 1, runtime 1 throughout |
| UR continuity | Three repeated controller timestamps retained; no claim that the earlier network issue is resolved |
| M05-A03 grasp retention / production actuation | NOT RUN |

The meaning of raw FLT=4 is unresolved: it is absent from the fault tables in
the inspected Hand-E manual and archived bridge example. Do not label it a
particular mechanical/communication fault, mask it as success, or equate it to
the later TCP read timeout. The last observed settings were POS=249, PRE=254,
SPE=51, FOR=51, ACT=1, STA=3, OBJ=3, GTO=1, COU=0, FLT=4.
The operator was told promptly that monitoring ended and asked to pause this
round. Next evidence needed: the pendant's Robotiq status/error text and the
installed URCap/Hand-E firmware version. No reset was requested or performed.

Local evidence: `artifacts/hande-manual-20260911/`, including exact monitor,
JSONL streams, identity, failure log, offline summarizer and summary. Remote
raw evidence: `/home/robot2026fall/hande-manual-20260911/`. Image `a3d22d1ffa6c`.
The [archived Robotiq bridge example](https://dof.robotiq.com/discussion/2420)
describes SPE/FOR as requested settings; production interpretation remains raw.

### Operator-open recovery observation (2026-09-11)

After the interrupted monitor, the user reported manually returning the gripper
to fully open and a normal blue indicator. A fresh, bounded GET-only diagnostic
using the original six-register Reader returned three identical polls:
`POS=3, PRE=0, STA=3, OBJ=3, FLT=0, COU=0`, taking 20.2-22.9 ms.
PASS for this open-state readback: the previous FLT=4 is no longer present.
Its meaning and the earlier timeout cause remain unresolved; do not erase the
failed 90-second-monitor result. No assistant-issued reset or actuation occurred.
This explicit subsequent diagnostic is not an automatic recording reconnect.
Evidence: `artifacts/hande-open-recheck-20260911/report.json` locally and
`/home/robot2026fall/hande-open-recheck-20260911/` remotely. POS=3 is an observed
open value, not yet a finalized endpoint calibration.

### Dynamic recording timeout recurrence (2026-09-11)

FAIL for sustained integrated readback: during operator-driven arm motion, the
read-only camera+UR+Hand-E recording aborted after approximately 27 seconds on
a Hand-E GET timeout. Recovered partial records show POS=3 and FLT=0 throughout;
no completed episode was published. The earlier timeout remains unresolved,
despite the successful short open-state and static-chain checks. No timeout
extension, reconnect, fault masking or gripper actuation was introduced.
See [M13 dynamic recording evidence](../m13-acceptance/readonly-integration.md).

### Read-only latency isolation (2026-09-11)

The user authorized diagnosing the timeout and offered to change modes manually;
physical control remains forbidden. Keep the initial mode unchanged to preserve
a baseline. Use a disposable probe under ignored `artifacts/`, outside production
recording: timestamp every GET request/reply, compare sequential six-register
polls with POS-only polls, and measure concurrent ICMP latency. Each phase runs
for at most 45 seconds plus bounded in-flight reads. Only the fixed six GET
registers and allowlisted Dashboard identity/status queries are sent.

Production uses one 250 ms deadline for all six sequential round trips. The
diagnostic probe allows up to two seconds per poll solely to observe late replies
and counts every poll exceeding the production budget as an overrun. It cannot
qualify recording acceptance; it performs no retry within a failed phase and
does not alter production timeouts, required fields or stale gates. A new
connection belongs to the explicitly separate comparison phase.

Keep the failure cause uncertain until timings distinguish network delay,
service response delay and total-budget exhaustion. Local versus Remote mode is
not a prerequisite for UR output monitoring on RTDE port 30004, according to
[UR's interface documentation](https://www.universal-robots.com/articles/ur/interface-communication/remote-control-via-tcpip/).
That statement does not establish the independent Robotiq bridge's mode behavior.

#### Isolation results

| Diagnostic | Observed result |
| --- | --- |
| Six-register GET, 45 seconds, no camera/RTDE workload | 364 polls; median 22.880 ms, p95 26.804 ms, maximum 95.114 ms; no 250 ms overrun |
| POS-only GET, 45 seconds, no camera/RTDE workload | 425 polls; median 5.112 ms, p95 6.478 ms, maximum 365.220 ms; one production-budget overrun |
| Concurrent baseline ICMP | 460/460 replies, no packet loss; maximum 203.664 ms. The approximately 204 ms reply arrived in the same interval as the 365 ms POS response |
| Full camera/RTDE/Hand-E recording with per-GET tracing | FAIL after approximately 19 seconds; first GET POS in a poll timed out after 250.470 ms with virtually the full 250 ms budget initially available; no episode completed |
| ICMP around the full-load failure | Approximately 388 ms and 182 ms replies in the same stalled interval; adjacent replies approximately 4 ms |
| Device ownership | GET/output-only throughout; no mode change, motion command, gripper SET or reset |

The load comparison used candidate-v2 on the same immutable image, with a
diagnostic-only `hande.py` overlay that logs each response or timeout. Its
recorded revision is `bbc56a8-working-cleanup-v2-get-trace`. The 250 ms production
deadline remained unchanged. The test requested two 30-second episodes, but the
first failed. Camera frame counts before shutdown were 586/586/585, and no
containers remained after cleanup. No operator motion was requested.

Conclusion: camera encoding and six-field accumulation are not necessary for
the observed overrun. A single required POS request can exceed the budget;
the full-load failure happened on POS before any auxiliary request. Concurrent
ICMP delay supports a shared communication-path or controller-response stall,
not a demonstrated Robotiq-only failure. This does not yet distinguish Wi-Fi,
routing, controller networking or controller load. No packet-loss claim follows
from delayed replies, and the successful baseline is not sustained acceptance.

The observed route from the collection PC to the controller uses Wi-Fi interface
`wlp3s0` through gateway `10.245.128.1`. The next proposed discriminating test is
a verified wired PC-to-controller path with the same GET/ICMP probe, followed by
full-chain recording. Network configuration changes require separate operator
coordination. Do not disable Wi-Fi, change routes, switch modes or increase gates
automatically. Remote mode remains untested and is not an established remedy.
Splitting auxiliary registers alone cannot fix the demonstrated POS delay.

Local and remote evidence directories are respectively
`artifacts/hande-latency-20260911/` and
`/home/robot2026fall/hande-latency-20260911/`: exact GET probe, instrumented reader,
launcher, JSONL request traces, ICMP logs and summaries. The failed loaded capture
remains at `/var/lib/ur12e-collection/data/readonly-latency-loaded-20260911/`.
Production source, image, station settings and gates were unchanged by this
diagnosis. No new mainline behavior was implemented.

### Wired-path retest (2026-09-11)

The user corrected the physical connection and authorized another read-only run.
Route inspection now resolves the controller directly through `enp128s31f6`,
source `10.18.1.243`, with no Wi-Fi gateway on that route. Dashboard identity
still matches the controller serial; Remote Control remains false. The assistant
made no network, mode or device-control changes.

PASS for this bounded persistent-read comparison. A ten-second six-register
probe completed 98 polls, median 2.860 ms and maximum 4.683 ms. The subsequent
full camera+UR+Hand-E run completed two 30-second episodes and clean shutdown.
Its 765 six-register polls / 4,590 GET requests had no timeout: whole-poll median
2.038 ms, maximum 4.917 ms; maximum individual GET response 1.878 ms. The original
250 ms poll and 500 ms supervisor stale bounds remained unchanged. Concurrent
ICMP returned 360/360 replies, with mean 0.210 ms and maximum 0.483 ms.

This comparison supports the previous Wi-Fi/routed path as the practical cause
of the reproduced latency problem; it does not identify a specific faulty cable,
access point or network component. The fault did not recur on the wired path in
this run. Each episode contains 293 Hand-E records, POS=3 and FLT=0 throughout;
changing gripper position and long-duration reliability are not established by
these fixed-gripper recordings. Existing earlier failures remain part of the
record rather than being reclassified as passes.

The same immutable image, candidate-v2 source and diagnostic per-GET trace overlay
were retained. No production deployment or source change was made. Evidence:
`artifacts/hande-wired-20260911/` locally and
`/home/robot2026fall/hande-wired-20260911/` remotely, including route, probe,
launcher, request traces, ICMP, session and offline feedback summaries. See
[M13 wired integration results](../m13-acceptance/readonly-integration.md).

### N3 offline command owner

The offline completion plan authorizes a command client on an injected connection
only; the physical read-only constructor and entrypoints remain unchanged.
Use bounded ASCII GET and SET, with an exact three-byte `ack` assembled across
partial reads. POS/SPE/FOR/GTO are sent together after active/fault-free readback.
An explicit activation request exists but startup/move never invokes it. Closing
or ending an episode sends no automatic release/reset. PRE and POS remain distinct
from the successful request. Local socket-pair tests cover fragmentation, failed
acknowledgement, inactive refusal and retained request on close. No real Hand-E
actuation or grasp-retention acceptance is claimed.

Protocol references: [Robotiq bridge archive](https://dof.robotiq.com/discussion/2420/control-robotiq-gripper-mounted-on-ur-robot-via-socket-communication-python)
and the [ur_rtde Hand-E example](https://sdurobotics.gitlab.io/ur_rtde/_static/robotiq_gripper.py).
The installed URCap version/target selection still needs lab verification.
