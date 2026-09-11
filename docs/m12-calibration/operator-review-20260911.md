# Passive leader operator review, 2026-09-11

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Primary: M12 / M04-A01 / M04-A03. This is offline evidence review, not calibration
activation or powered-motion acceptance. Camera/resource investigation remains
deferred. No hardware connection or control command was opened for this review.

## Evidence and correction

Reviewed `artifacts/gello/operator-batch-20260911T142353`, protocol
`passive_150s_v3`. The two earlier runs (`142107`, `142318`) ended with
KeyboardInterrupt and remain incomplete; their samples are not stitched into the
completed run. The operator reports wrist2's A/B movements were reversed.

`analysis.json` is the unmodified schedule-based review. The additional
`analysis-operator-corrected.json` swaps only ID5's semantic A/B observations and
retains the operator correction, source-file SHA256 hashes and pending fields.
Raw samples, events and hardware configuration are unchanged. This correction
does not invert a motor register, change a stored calibration or establish a
UR-positive direction. `diagnostic-1s-bins.json` supplies temporal diagnostics,
not replacement acceptance windows.

## Transport and reference

PASS: 150 s, 8,161 groups, 54.404 Hz. Source-gap p99 30.084 ms, maximum 53.554 ms;
no communication/status errors, no sequence/epoch discontinuity. All 147 health
observations report torque off and hardware error zero. The wire ledger contains
only 14 READ and 8,309 SYNC_READ instructions. All 37 cues were emitted, maximum
emission lateness 6.085 ms. This measures cue emission, not audio playback or
operator reaction timing. It establishes isolated dynamic readback, not combined
camera/control-load acceptance.

The final two seconds of the initial reference contain 108 samples, with raw
centers `[3113,2120,3187,1037,42,1971,3256]` and spreads `[0,1,0,0,0,1,0]` counts.
This is a usable stable relative-input reference. The operator did not supply the
HOME declaration flag; its geometric identity remains unverified. Exact leader
HOME equality is not required by the agreed follower-HOME-relative mapping.

## Movement interpretation

Every expected motor channel responds during its named slot. Candidate count
changes for the instructed motor-side A direction, with the reported wrist2
reversal applied, are `[+,-,+,+,+,+]`. These are operator-view observations, not
validated UR signs or proof that every hold window is stable. Shoulder activity
also includes appreciable elbow movement; do not infer a faulty motor or a fixed
mechanical coupling from passive handling alone.

| Axis | Original A / B median delta from initial reference, counts | Hold spread A / B, counts | Interpretation |
| --- | --- | --- | --- |
| ID1 base | +333 / -37 | 5 / 100 | Opposite movements visible; B return overlaps its nominal hold |
| ID2 shoulder | -302 / +443 | 16 / 4 | Opposite sign to the other candidate A directions; elbow also moves |
| ID3 elbow | +251 / -90 | 6 / 10 | Input responds; passive movement does not clear its powered cable block |
| ID4 wrist1 | +410 / -214.5 | 2 / 403 | A is stable; B window contains return motion |
| ID5 wrist2 | -471 / +262 | 1 / 14 | Operator-reversed A/B; corrected semantic deltas are +262 / -471 |
| ID6 wrist3 | +7 / -54 | 320 / 711 | Medians are not endpoints because actual movement overlaps both holds |

Wrist3's full slot clearly contains a positive excursion (about 1972 -> 2343)
and a negative excursion (down to 1299). Its positive movement starts late in the
scheduled A hold, and return overlaps the B hold. Do not use the schedule-based
+7-count median as its motion amplitude or claim stable endpoint acceptance.

Final whole-arm reference minus initial reference, in counts:
`[-38,+6,+6,+10,+18,+106,-27]`. The six arm offsets correspond to approximately
`[-3.34,+0.53,+0.53,+0.88,+1.58,+9.32]` encoder degrees. These are manual-reference
return differences, not powered HOME errors or actuator accuracy measurements.
The final reference still has up to 25 counts of wrist1 variation. No accuracy
tolerance is relaxed on the basis of this run.

## Lever and signed-coordinate findings

The fixed OPEN window has median 3245 but spread 254 counts: it contains motion,
so 3245 must not become the OPEN calibration endpoint. The lever reaches around
2571 shortly afterward, but that short diagnostic plateau does not satisfy the
agreed stable window. CLOSED=3388 has a 1-count spread over the selected window.
The clockwise-close convention is consistent with this run's lever sequence;
retain a CLOSED candidate, leave OPEN and repeated-approach acceptance pending.

ID5's observed range is **-433..308**, with 362 samples below zero and no adjacent
jump over 2048 counts. The negative segment is continuous, not evidence of serial
corruption. The [official XL430 manual](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#present-position132)
states that torque-off Present Position is signed continuous 32-bit feedback,
regardless of operating mode. Enabling torque in position mode, changing to
position mode, or reboot/power-on can reset it into a single-turn representation,
with Homing Offset still applicable.

This exposes a software limitation: the current `mapping.Joint`/reference
validation assumes 0..4095 for calibrated input. That restriction must not be
applied indiscriminately to valid torque-off feedback. Keep signed logical input
coordinates distinct from powered position-mode goal coordinates and actual
mechanical bounds. Explicitly verify coordinate re-establishment on torque/mode/
power transitions before commanding HOLD/HOME. Do not silently modulo negative
inputs or simply remove physical limits. This review documents required follow-up;
no runtime implementation or motor configuration was changed.

## Conclusions and minimal next work

- PASS: isolated full-arm input acquisition and a stable initial reference;
  expected seven-channel responses are observable.
- PARTIAL: motor-side direction observations, including the operator's wrist2
  correction. UR sign comparison remains unverified.
- FAIL / pending: fixed-window stationary acceptance for several axes and OPEN
  lever endpoint; CLOSED has one stable candidate, not repeatability acceptance.
- NOT RUN: powered command reception, HOLD/HOME, torque-transition alignment,
  complete activated calibration and integrated URSim following.

First address signed-input versus powered-goal coordinates in software. Then
use one consolidated short observation to capture stationary lever endpoints
and any needed wrist3/reference confirmation, rather than repeating all six
large excursions. Compare directions against an explicit UR reference separately.
No active calibration file was published, and no motor or physical UR command
was sent during analysis.

## Subsequent operator decisions: HOME and lever

The operator clarified HOME semantics after this review. Initial/final reference
postures define the intended HOME, not intermediate A/B medians. The initial
reference is selected as authoritative for this run: actual sample sequence 273,
raw arm `[3113,2120,3187,1037,42,1971]`. It is the last fully acquired sample in
the initial reference hold. Its epoch and exact acquisition interval are retained
in `home-and-lever-decisions.json`; no averaged pose is used. The standalone
reference analyzer now also selects an actual final sample after its stability
check, and batch return comparisons use actual reference samples.

Final sample sequence 8160 is `[3076,2127,3190,1040,60,2078]` for the arm. The
measured differences are `[-37,+7,+3,+3,+18,+107]` counts, including about 9.40
encoder degrees on wrist3. The intended poses may be the same, but these actual
samples are not equal. The final sample is return-check evidence only; it neither
replaces nor averages into HOME. These remain manual return observations.

The operator allows arbitrary independent lever conventions and accepts 3388 as
the CLOSED input value. Software OPEN is assigned 3256, the initial lever count;
CLOSED is assigned 3388. The intended mapped output is 0..255 with saturation
outside those assigned endpoints. No claim of physical endpoint calibration,
repeatability or exact gripper travel is made. This supersedes the requirement
to obtain a mechanically stable OPEN extreme before defining software input.
Saturation and signed-coordinate motor handover remain implementation follow-up;
no physical motor command or active calibration was published.

Decisions are saved in the run's `home-and-lever-decisions.json` and ignored
`config/local/gello-reference.json`. Raw evidence remains unchanged. Validation:
39 focused mapping/reference/source/batch tests passed; Black and Pylint passed,
with no findings. No hardware connection was opened for this update.
