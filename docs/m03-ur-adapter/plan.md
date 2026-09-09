# M03: Read-Only UR Inventory and State Probe

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Module: M03
- Status: implemented / hardware acceptance pending (read-only slice)
- Parent: [meta plan](../../meta_plan.md)
- Dependencies: M01; robot address supplied by the user
- Updated: 2026-09-09
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

The camera diagnostic refinement shares a small bounded worker-cleanup helper with this probe. It allows a reported worker to exit, then uses bounded terminate/kill joins. No UR query or control behavior was added; the read-only software checks pass after this refactor.

The diagnostic command is implemented. Software tests verify the fixed read-only Dashboard allowlist, socket timeouts, failure reporting, and preservation of existing output files. Actual UR identity and RTDE acquisition remain NOT RUN because the controller IP is pending. The station Ethernet link is up but has no IPv4 address at inspection; configure the dedicated robot subnet after the user supplies the robot address. M03-A02 stop/hold and M03-A03 controller-side fault handling are NOT IMPLEMENTED and cannot be accepted by this probe.
