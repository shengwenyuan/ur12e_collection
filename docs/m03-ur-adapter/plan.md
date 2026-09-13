# M03: Read-Only UR Inventory and State Probe

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Module: M03
- Status: implemented / hardware acceptance pending (read-only slice)
- Parent: [meta plan](../../meta_plan.md)
- Dependencies: M01; user-confirmed UR12e controller address `10.18.1.106`
- Updated: 2026-09-10
- Alignment: the user approved prioritized on-site UR identity/software/state inspection on 2026-09-09. Joint targets remain unknown and no motion test is included.

## Scope and design

Add `devices ur --host ADDRESS --seconds N --output FILE`. Query the Dashboard server on TCP 29999 using read-only `PolyscopeVersion`, `get serial number`, `robotmode`, and `safetystatus`. Preserve unsupported/error responses rather than inferring identity. Socket connect/read operations have bounded timeouts.

Read actual joint position, velocity, motor current, TCP pose (meters plus rotation vector in radians), robot/safety mode, controller timestamp, and host receipt time through `rtde_receive`. Never instantiate RTDEControl, send URScript, load/play programs, activate the gripper, unlock protective stops, or change robot mode. A separate bounded worker contains SDK connection/read stalls; terminate only this diagnostic worker on timeout. Robot-side stop/hold and watchdog implementation remain future work.

The diagnostic sampling interval is not a servo-loop commitment or production timestamp association. Preserve source time separately from receipt time; repeated source timestamps are observable. Save the raw report outside Git, with no synthetic missing values. Endpoint availability is separate from actual feedback success.

## Acceptance

| Case | Criterion | Environment |
| --- | --- | --- |
| M03-A01.1 | Actual Dashboard/software identity and RTDE fields are captured with explicit errors | Real UR, read-only; no motion |
| M03-A01.2 | Invalid address, unavailable server, and worker timeout return bounded failures | Software fixtures |

## Results and remaining work

### TODO: Active TCP offset and flange pose

Status: **TODO / not implemented**, explicitly requested for future unfinished-work
summaries on 2026-09-12. Primary scope: M03-A01; related: M10-A03 and M12 pose
semantics. Current recordings contain base-to-active-TCP pose, but the adapter
reports `controller_active_value_not_read_back` for the offset.

Updated alignment, 2026-09-13: the operator confirms zero Installation TCP for
the discussed recordings and a separate physical tool extension of 127 mm along
flange-local z. Preserve the interface TCP unchanged and persist static offset
metadata with explicit frames/units/operator provenance; leave flange conversion
to downstream cleaning. Controller readback is not a prerequisite for accepting
an explicitly operator-declared installation. Do not conflate the zero active
offset with the physical extension, or assume either is verified for future runs.
No numeric offset field has been implemented yet. See the
[M10 coordinate/timing clarification](../m10-data-contract/plan.md#tcp-installation-and-hand-e-timing-clarification-2026-09-13).

Before implementation, align the field/schema and offset-change handling.
Acceptance must cover zero/nonzero translation and rotation, unavailable offset,
offset changes and preservation of historical recordings. Controller/SDK support
and physical read-only acceptance remain unverified for this addition. No code
change or device access is authorized by this tracking entry.

The user-reported [actual unit inventory](controller-inventory.md) records UR
Software `5.22.1`, controller hostname/serial, component versions and installed
URCaps. The pendant reports DHCP and `Not connected to network!` despite reported
ping reachability. Reconcile this discrepancy and compare independent identity
readback with the inventory; these observations do not satisfy M03-A01.1.

The camera diagnostic refinement shares a small bounded worker-cleanup helper with this probe. It allows a reported worker to exit, then uses bounded terminate/kill joins. No UR query or control behavior was added; the read-only software checks pass after this refactor.

The diagnostic command is implemented. Software tests verify the fixed read-only Dashboard allowlist, socket timeouts, failure reporting, and preservation of existing output files. At the initial inspection the controller IP was unknown. On 2026-09-10 the user identified `10.18.1.106` as the UR12e controller. Read-only ICMP checks passed from Mac and the collection PC (three replies each, no packet loss). The collection PC reached it through its Wi-Fi gateway; a dedicated Ethernet subnet is not a prerequisite for basic reachability. Dashboard identity and RTDE acquisition remain NOT RUN in this address-confirmation check. Ping does not establish identity, controller mode or control-loop suitability. M03-A02 stop/hold and M03-A03 controller-side fault handling are NOT IMPLEMENTED and cannot be accepted by this probe.

## Read-only integration increment

Read-only preflight captured the configured serial, Dashboard status and 60 RTDE samples. Persistent output-only acquisition is implemented and software-tested; its new-image physical integration remains NOT RUN. The powered-off raw zero values do not establish physical joint posture. See the
[shared plan and results](../m13-acceptance/readonly-integration.md).


## URSim control increment

M03-A01/A02/A03 simulator portions now PASS: progressing readback, bounded
move/servo stop, held drift, client loss, stall watchdog and explicit native
Home/SDK ownership. Shared transport code remains separate from a physical
connection factory, which is disabled. See the current
[M06 control results](../m06-control-motion/simulator-control.md). The earlier
read-only statements above describe the diagnostic command, which remains GET/output-only.
Physical control acceptance remains NOT RUN.


## Powered Manual-mode readback (2026-09-11)

The [live-state check](live-state-20260911.md) passes the short M03-A01 read-only
scope on the deployed current image: registered serial/software, Manual/Local,
normal safety, stopped program and 150 feedback observations. One getter sample
crossed a timestamp update and remains explicitly marked; no atomic sample-rate
acceptance is inferred. Raw model query is `UR10`; physical unit identity remains
the user-registered UR12e with matching serial. No real control or configuration
change was performed, and physical motion remains prohibited.

The subsequent 30-second static recheck in the same live-state record confirmed
identity, Manual/Local, a stopped program and a near-READY stationary pose.
Feedback continuity did not pass: 27 repeated source timestamps and a maximum
256 ms source-time jump require read-only diagnosis. The PC currently routes
through Wi-Fi. Production station identities remain unset; no motion acceptance
or configuration change follows from this diagnostic. Each next test requires
alignment of verification points and operator steps; the user performs physical
start/motion actions and the assistant must not send physical control commands.

The extended receive-only preflight in that record adds runtime, target
kinematics, speed-scaling and payload readback. Its 10-second sample window
passes continuity without resolving the earlier intermittent failure. The
controller currently configures 5 kg and zero CoG; actual tool assembly matching,
active TCP, pendant Home parameters and all physical motion checks remain pending.

Operator-driven physical wrist3 motion was observed in a 60-second receive-only
run. Direction/selectivity readback passed, but actual speed peaked at 20.08 deg/s,
above the proposed 1 deg/s test setting; final posture was paused near +4.90 degrees.
No assistant-issued control occurred. See the [operator motion record](../m06-control-motion/operator-motion-check.md).
This does not accept low-speed control, final READY return or timed interruption.

The operator accepts the subsequent basic wrist3 demonstration: M03-A01 physical
motion readback, slow outward movement and observed post-pause stability are
recorded separately from full control acceptance. Fast return motion remains
measured and its source unverified; the originally proposed round-trip low-speed
criterion did not pass. See the operator acceptance clarification in M06.


### Operator-declared TCP geometry, 2026-09-13

The operator supplies translation (0, 0, 0.127 m). Confirmation of the local frame,
relative orientation and whether this is the active UR installation setting is
pending. Retain it as a declared geometry value, not verified controller readback.
Joint-space teleoperation/recording can proceed independently; current MCAP still
records base-to-active-TCP only and must not claim a derived flange pose.
