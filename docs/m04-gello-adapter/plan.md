# M04: Unavailable GELLO Interface Stub

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Module: M04
- Status: implemented / physical acceptance pending (stub only)
- Parent: [meta plan](../../meta_plan.md)
- Dependencies: M10 contract foundation
- Updated: 2026-09-09
- Alignment: the user explicitly requested GELLO stubs while its parallel hardware development remains blocked, and authorized foundation implementation on 2026-09-09.

## Scope and acceptance

Expose `health`, `read_state`, `move_to`, `hold`, and `stop` on an unavailable implementation. Health is never ready, state is absent, and all control requests raise an explicit unavailable error. It does not fabricate joint values, open serial ports, report a successful hold, or silently become a simulated leader. Actual DYNAMIXEL communication, mapping, torque transitions, and load acceptance remain unimplemented.

Case M04-A04.1: software tests verify missing state and rejected control requests without any socket or device access. This is the fake-device isolation portion only; it does not accept M04-A01 through M04-A03 or the load/thermal portion of M04-A04.

## Results

The unavailable API is implemented. M04-A04.1 is covered by the software suite: no ready state or invented feedback, no network calls, and explicit failure for move/hold/stop. Physical GELLO acceptance remains blocked by parallel hardware work.
