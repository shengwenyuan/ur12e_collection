# M15: Disabled Policy and Explicit Authority Interfaces

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned / implementing under N5 of the 2026-09-11 offline completion plan.

Define an observation-provider protocol and a disabled policy source. Reading a
policy target or requesting takeover/resume raises an explicit unavailable error.
Do not add policy transport, inference, action chunks, automatic resume, keyboard
bindings or another control owner. Existing M10 acquired/released events retain
source identity and reason for a future separately aligned handover workflow.

M15-A01: disabled interfaces cannot produce targets or call any device transport.
M15-A02: future handover descriptions preserve source and reason without changing
ordinary demonstration semantics. Actual policy execution remains out of scope.

## Software results

M15-A01/A02 interface tests PASS: disabled target reads and takeover requests
raise without a transport, while immutable handover descriptions retain distinct
owners and a required reason. No policy runtime or new authority grant exists.
