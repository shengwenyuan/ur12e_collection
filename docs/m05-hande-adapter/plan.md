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
