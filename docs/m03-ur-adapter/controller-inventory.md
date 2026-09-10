# UR12e and Hand-E: Actual Unit Inventory

Recorded: 2026-09-10. Source: user-reported pendant information. These details
have not been independently read back in this documentation update and do not
constitute M03 or M05 hardware acceptance.

## Controller identity and software

| Pendant field | Reported value |
| --- | --- |
| Robot model | UR12e |
| UR Software | `5.22.1` |
| Hostname | `ur-20255100083` |
| S/N | `20255100083` |
| Baseline | `12.14.860` |
| Polyscope | `74.22.248` |
| Controller | `73.26.48` |
| Firmware | `47.3.95` |
| Platform | `0.1.1` |

Preserve the labels as reported: `UR Software` and the component field
`Polyscope` are separate entries, not interchangeable version numbers.
The `Firmware` entry belongs to this controller version screen; it is not a
Hand-E firmware readback.

## Installed URCaps and gripper

The pendant lists these installed URCaps; their individual versions have not
been reported:

- `Remote TCP & Toolpath`
- `UR Connect`
- `External Control`
- `Robotiq_Grippers`

The attached gripper model is Robotiq Hand-E. Its serial number, firmware,
wiring, device ID and installation-page recognition remain unverified.
`Robotiq_Grippers` being listed establishes the reported package presence, not
successful gripper communication or availability of the candidate TCP bridge
on port 63352. See [M05 communication notes](../m05-hande-adapter/communication-notes.md).

Likewise, installed `External Control` does not establish its configured host,
an active robot program, or readiness to accept motion commands.

## Network observation

| Item | Observation |
| --- | --- |
| Address configuration | DHCP, as reported by the user |
| Pendant message | `Not connected to network!` |
| Reachability | The user reports that the current IP responds to ping |
| Previously confirmed controller address | `10.18.1.106`, confirmed on 2026-09-10; recheck the current lease under DHCP |

The pendant message and reported IP reachability remain an unresolved status
discrepancy. Do not infer its cause or treat ping as controller identity,
Dashboard/RTDE availability, or Hand-E service acceptance. The earlier bounded
ICMP checks are recorded in the [M03 plan](plan.md).

At the next robot inspection, reconcile the pendant's current address/subnet,
DHCP lease, hostname/serial readback and displayed network status, then record
bounded read-only Dashboard, RTDE and gripper-service results separately.
This inventory update does not change network settings or enable motion.

This unit-specific reference is versioned at the user's explicit request.
Runtime station identity and network bindings remain in the local station
configuration; this document is not a deployment default.


## Independent powered readback (2026-09-11)

The [bounded current-image diagnostic](live-state-20260911.md) independently
confirmed endpoint `10.18.1.106`, serial `20255100083` and software
`5.22.1.1214860`. The controller is Manual/Local, reports normal safety and a
stopped program. Dashboard's model query returns `UR10`; this raw naming does
not replace the physically identified UR12e or qualify a different control model.
Component-screen fields, URCap versions and gripper identity remain unverified.
No physical control, mode change or configuration update was sent.
