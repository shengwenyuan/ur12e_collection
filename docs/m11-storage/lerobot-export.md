# M11: Retired LeRobot Export

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: retired on 2026-09-12 by explicit user direction. LeRobot conversion is
owned by a different repository. This collector produces verified MCAP plus
JSON only; the `episode export` CLI, exporter/projection implementation,
export-only tests and optional exporter requirements were removed.

Historical software acceptance used official LeRobot 0.6.1 for a camera-anchored
30 Hz RGB/arm projection. It did not preserve every 120 Hz action row and is not
a current high-rate training interface. Previously produced datasets, source
recordings and immutable release archives are retained unchanged. See Git
history for the retired implementation and its original test evidence.

Neutral MCAP reading and SHA-256 helpers remain in `mcap_read.py` for verification,
replay and the M14 trajectory interface. The external consumer must preserve
source timestamps and distinguish leader intent, sent commands and measured
feedback. Dataset frequency, action windows and training normalization belong
to that consumer.
