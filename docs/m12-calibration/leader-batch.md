# One-session passive leader calibration

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / operator capture pending. Primary: M12; related: M04-A01,
M04-A03. The user requested one guided session with offline log review, then
explicitly shortened it to 20 seconds per motor with no preparation delay on
2026-09-11. The 150-second protocol supersedes the previous 80- and 250-second schedules.
See the [M04 integration plan](../m04-gello-adapter/hardware-integration.md).

## Run once

Secure the base and support the arm. This program never enables holding or moves
a motor. The operator is already positioned; the first five seconds only capture
a stationary reference. Use HOME only if it can be reached and supported with
free cable clearance. Otherwise retain a stable reference and report it as such.

```bash
.venv/bin/python -m ur12e_collection.calibration.leader_batch \
  --port /dev/cu.usbserial-FTBEQCDG --baudrate 3000000 \
  --output "artifacts/gello/operator-batch-$(date +%Y%m%dT%H%M%S)" --speak
```

Run from the repository in the provisioned Mac environment. Add `--home-declared`
only for an operator-confirmed HOME reference; this is not independent geometric
validation. Omit `--speak` for text/terminal-bell prompts. No camera, follower or
other serial application needs to be started. Use a new output directory.

| Time | Action |
| --- | --- |
| 0-5 s | All joints stationary at the supported reference |
| 5-25 s | ID1 base |
| 25-45 s | ID2 shoulder |
| 45-65 s | ID3 elbow; keep still if cable clearance is uncertain |
| 65-85 s | ID4 wrist1 |
| 85-105 s | ID5 wrist2 |
| 105-125 s | ID6 wrist3 |
| 125-145 s | ID7 gripper-input lever |
| 145-150 s | All joints stationary at their original reference |

Each arm slot: move A for 4 s, hold A for 4 s, move B across the starting reference
for 4 s, hold B for 4 s, return for 4 s. View from the motor output-shaft end toward
the motor: A is counterclockwise, B clockwise. Use comfortable excursions around
5-10 degrees on each side, within free mechanical and cable travel. Approximate
excursions do not verify scale. Move only the named joint; skip any uncleared
motion instead of forcing a cable or hard stop. ID3 powered motion remains blocked.

ID7 is a motor with a lever, not a jaw. For this run, its counterclockwise-side
position represents OPEN (Robotiq raw 0), clockwise-side position CLOSED (255).
This is a reversible software convention. Its slot is: move counterclockwise 4 s,
hold OPEN 4 s, move clockwise 4 s, hold CLOSED 4 s, return 4 s. Do not force stops.
One pass collects candidates; repeated-approach accuracy remains unverified.

If `CAPTURE STOPPED` appears or prompts cease unexpectedly, stop manual motion
and retain support. Ctrl+C also closes this read-only capture, without providing
powered holding. Send one completion/abort message with skipped axes and whether
the reference was HOME. No per-axis chat response is needed.

## Offline evidence and limits

```bash
.venv/bin/python -m ur12e_collection.calibration.leader_review \
  artifacts/gello/OPERATOR_RUN --output artifacts/gello/OPERATOR_RUN/analysis.json
```

Logs retain planned phases, actual cues, raw seven-axis position/velocity and
independent health. Local monitoring only checks health, freshness, torque-off
and cue deadlines; movement analysis is offline. A cue delayed more than 500 ms
aborts rather than relabeling later actions.

Use only actual hold intervals, never adjacent movement. Each analyzed window
needs at least 30 samples spanning one second, with no >100 ms sample gap. Keep
epoch/order checks and report branch jumps, A/B deltas, other-axis movement,
hold spreads, gripper endpoint candidates and initial-versus-final reference
errors. The compressed schedule has no separate per-axis return hold. Do not
mislabel its final whole-arm return error as an independently held per-axis test.
Three-approach repeatability cannot pass from one OPEN/CLOSED cycle.

Passive logs alone cannot verify UR-positive directions, precise geometric HOME,
exact gearing, full mechanical limits or powered arrival. Those fields remain
unverified; no active calibration is overwritten. Consolidate missing physical
facts into one follow-up after the batch.

## Validation

PASS: 27 focused source/calibration tests, including the full virtual 150-second
sequence, offline candidates, no invented repeatability, epoch rejection, torque
and disconnect/interrupt failures, and late-cue rejection. Black and Pylint passed.
NOT RUN: the compressed operator batch on hardware. No motor write was issued.
This native Mac increment has not been rebuilt into the Docker development image.
