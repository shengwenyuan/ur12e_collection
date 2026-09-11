# M14: Read-Only Trajectory Interfaces

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned / implementing under N5 of the 2026-09-11 offline completion plan.

Provide a null sink and a bounded mailbox using the existing observation interface
(`records`, `status`, `close`, `health`). It receives detached command, feedback,
authority and phase events; it has no control transport or lease. Overflow counts
lost optional telemetry without blocking collection. A consumer may drain events
and export separate commanded/measured trajectories using preserved units/clocks.
An absent/stalled consumer cannot affect the control or authoritative MCAP path.
Isaac Sim scenes, synchronization and physical-model validation are excluded.

M14-A01: preserve source kind, provenance and commanded/measured distinction.
M14-A02: full/closed mailboxes and absent consumers cannot delay or acquire control.
Software tests and local export are required; no digital-twin runtime acceptance.

## Software results

M14-A01/A02 software PASS: a stalled one-slot mailbox loses only optional events
while the shared session continues sending commands and recording. Close performs
no device operation. `ur-collect episode trajectory EPISODE --output DIRECTORY`
independently verifies MCAP and publishes separate typed JSONL records plus a
manifest with source hashes, units, immutable snapshot and disposition. The
existing 8-second recorded-image/URSim episode exported successfully, including
its explicit discarded disposition; this diagnostic export is not training data.
