# Latest Camera Wiring Recheck: 2026-09-10

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: PASS for the latest wiring recheck. The user accepted six completed
40-second episodes as sufficient and requested stopping the remaining batch.
The user requested committing the validated fixes, then testing the latest
physical wiring/layout. This camera-only run uses commit `e294db5` for the
session/shadow overlays and the same explicit experimental performance profile
as the [previous batch](../m08-frame-matching/resource-gates.md).
Production defaults, station configuration and robot motion remain untouched.

## Reproduction and connection change

Use the previously verified base image
`sha256:8c393dd43cb8aaec6986489c0990a48aaf3f4eed43673b549b869de67563cbd2`
with byte-checked session/shadow source overlays from the commit, plus the
unchanged disposable timing wrapper. The immutable `run-layout-v1.sh` launcher
records revision `e294db5-timing-profile`. Its arguments are:

```text
layout-recheck-01 75 1 final 2 memory drain
layout-batch20-01 75 1 final 20 memory drain
```

The profile uses 640x480 RGB8/Z16 at 30 Hz, 16.7 ms matching skew, 75 ms
receipt-to-decision wait and capture-tail drain, 1 ms empty polling, final-file
pixel verification, and 4 GiB memory without CPU quota. Evidence lives under
ignored `artifacts/experiments/timing-20260910/` and
`artifacts/experiments/layout-recheck-20260910/`; full MCAP files remain on the
collection PC under `/var/lib/ur12e-collection/data/timing-20260910-<run>/`.

D405 now enumerates as USB 3.2 / 5000M on bus 004 port 007. Both D435IF units
now enumerate as USB 2.1 / 480M: one on bus 003 port 012 and one beneath the
hub on bus 003 port 013, child port 004. All three still advertise and run the
required RGB-D mode. These are observed link speeds, not proof of stability
or a guarantee for other profiles. Physical third-view left/right semantic
bindings remain unconfirmed.

## Completed smoke

Both exact 40-second episodes completed with launcher exit 0. Accepted groups
were 1196/1199 and 1198/1199, aggregate 99.8332%. Every in-window wrist receipt
had exactly one decision. All three sources ran approximately 30 Hz with zero
color/depth gaps and depth repeats. All RGB decoded and all depth hashes
verified. Writer queue peak was 1/4. Total MCAP storage was 865,164,592 bytes.
The smoke passes the applicable quality/accounting gates; it does not satisfy
the 20-episode duration gate by itself.

## Full batch

The user explicitly shortened this recheck to six completed episodes. By the
time SIGINT was delivered, seven episodes had finished; the eighth partial was
aborted and retained. The launcher exited 130 and the report truthfully remains
`interrupted`. This was a requested stop, not a camera failure. It does not claim
a second 20-episode pass or replace the earlier completed 20-episode evidence.

The first six accepted 7,187/7,198 anchors (99.8472%). All seven completed
episodes accepted 8,384/8,398 (99.8333%); the worst episode achieved 99.75%.
Every completed-episode wrist receipt had exactly one decision; consecutive
rejections peaked at one. All RGB frames decoded and all 25,152 depth hashes
verified. Sources had zero color/depth gaps and repeats across approximately
11,200 frames per camera, including finalization and the interrupted tail.
Writer queue peak was 2/4. Instrumented group work p95 was 22.95 ms (including
the partial episode); no overflow, OOM or CPU throttling occurred.

Seven completed MCAP files totaled 2,991,865,904 bytes, approximately 38.5 GB
per recorded hour for this scene. Final verification averaged 11.84 seconds
per completed episode. All camera test containers stopped, and the production
station SHA-256 remained
`17c3b9e2e505972f90a2dc0add6ea64f23cdd830dda1154f60c015b24424bb9c`.

This passes the user-approved latest-wiring link test using the experimental
profile. Production-default adoption, physical left/right binding, image framing,
physical clock accuracy and robot-motion acceptance remain separate.
