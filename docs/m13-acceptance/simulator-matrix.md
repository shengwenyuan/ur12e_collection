# Current Module and Simulator Handoff

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Updated: 2026-09-11. The current offline sprint uses recorded leader input,
recorded or synthetic RGB-D and official URSim. No physical device writes or lab
SSH occur. This table supersedes older availability summaries; historical lab
acceptance keeps its original revision and scope.

| Module | Implemented behavior | Current software/simulation evidence | Remaining physical or delivery gate |
| --- | --- | --- | --- |
| M01 | Pinned Ubuntu 24.04 / ROS 2 Jazzy, non-root unified development/runtime image, mounted station/data and offline bundle | Previous `ec64004` current image is deployed; new candidate checks are N7 | Rebuild and verify the new source-matched candidate, then lab software deployment |
| M02 | Strict configuration, atomic updates, camera mount and leader assembly identities, versioned activation/invalidation | Bad identity, stale calibration, changed HOME/assembly and failed replacement tests PASS | Confirm real setup identities; no physical calibration attestation is inferred |
| M03 | Read-only UR state; authorized control transport shared through one owner | Existing actual URSim motion/readback and prior lab readback/READY interruption evidence retained | Real coordinated teleoperation and physical disconnect/watchdog acceptance remain open |
| M04 | Persistent read-only DYNAMIXEL acquisition; signed calibration; immutable episode delta; conditioned target; injected HOME/HOLD coordinator | Passive capture and 3 Mbps migration previously observed; new replay, source-fault and stateful motor tests PASS | No physical motor-write transport in this sprint; ID3 cable, torque profiles, supported holding, powered coordinate binding and accuracy remain open |
| M05 | Read-only raw URCap registers; explicit authorized-socket command client; request versus measured feedback | Local wire fixture tests PASS, including bounded acknowledgements and no implicit release | Full shared sessions explicitly bypass Hand-E; live command/contact/retention tests pending |
| M06 | Exclusive native Home/SDK ownership, configured limits, actual stopped handover and fault latch | Actual URSim replay motion and source/recorder faults PASS; new coordinated leader handover uses fake motors | Physical HOME route, motion limits, motor support and coordinated arrival require lab validation |
| M07 | Persistent RealSense rig; three recorded RGB-D producer fixtures under tests | Prior physical camera slice retained; real-image replay files independently decode | Replay omits USB and SDK alignment cost; new-image camera smoke and labels remain lab work |
| M08 | Wrist anchors, 16.7 ms skew, 75 ms wait/drain, bounded buffers and no accepted reuse | Matching/failure tests PASS; single strict real-image 40 s run PASS; repeated full-load attempt FAIL | Mac amd64 long-load stability is not accepted; unchanged gate must pass on Ubuntu |
| M09 | Space HOME/start/stop, held review, `a` discard, Ctrl+C and fault latch; leader coordinator shares this lifecycle | Short replay sessions and leader/recorder faults PASS; fresh 20 x 40 s control batch running | Real leader/Hand-E coordination remains pending |
| M10 | Separate raw acquisition, desired intent, conditioned sent target and actual feedback; immutable baseline/calibration; original versus replay clocks | Independent MCAP audits and mutation tests PASS; prior read-only ROS observer evidence retained | Physical sign/scale validation and verified TF publication are separate gates |
| M11 | Streaming H.264/uint16 PNG MCAP; bounded writer; optional three camera encoding workers; official v3 RGB/arm export | Codec/corruption/atomic-write tests PASS; real replay round trips exact depth; serial/parallel payloads match | Real-image sustained throughput remains open; gripper/depth training projection is outside this sprint |
| M12 | Offline board solver and held-out checks; taught traversal with 2 s stationary capture; parallel leader configuration workflow | Native geometry/config tests PASS; actual URSim 20 checkpoints / 30 synthetic image-readback pairs PASS | Real board geometry, TCP offset, taught routes, visibility and accuracy thresholds remain open |
| M13 | Shadow, isolated actual URSim checks, strict independent episode audit and fault campaigns | Current native baseline 389 PASS / 5 environment skips; updated batch/release gates in progress | Full-load replay failure is retained; new Ubuntu/device acceptance NOT RUN |
| M14 | Verified typed trajectory export and bounded optional observation mailbox | Export from completed MCAP PASS; stalled/full mailbox cannot own or block control | Isaac scene/integration is interface-only future work |
| M15 | Disabled policy interface and explicit future handover requests | Policy cannot issue commands; handover metadata does not grant ownership: PASS | Policy inference and takeover behavior require future alignment |

## Current behavior and resource boundaries

One follower READY/HOME target remains `[0, -90, -90, -90, 90, 0]` degrees.
Each episode binds a new stable leader baseline to that HOME and preserves the
baseline in its authority record. Signed encoder coordinates are not wrapped.
Desired intent and derivative-bounded commands are archived separately; the
conditioner does not claim an explicit jerk limit. The 60 Hz leader setting and
50 Hz command cadence remain unchanged; replay timing is not a new serial-rate
measurement. More than 100 ms without valid input faults the session.

The leader HOME/HOLD fixture requires measured arrival within two counts for
200 ms. This tests sequencing and refusal behavior, not real motor accuracy.
Physical ID3 active motion remains blocked. No automatic torque release occurs
on close, stop or fault; torque-off engagement requires explicit verified support.
The shared simulation session keeps Hand-E unavailable/bypassed, with null actual
feedback rather than invented object or grasp state.

Space performs only the action allowed in the current phase. Stop holds the
follower, requests leader current-position HOLD and waits before finalization.
A normal stop leaves task success unknown. `a` preserves files with a discarded
outcome; Ctrl+C and faults retain unfinished data as partial. Recovery requires
an explicit new engagement. Optional ROS/twin observers never acquire control.

Recorded-image replay uses three bounded producers and three independent camera
encoding jobs in the recorder process; each codec has one worker. The MCAP writer
remains single-owned. Control never waits for image encoding. RealSense hardware
defaults remain unchanged. The Mac replay client uses a 5 GiB cap, a prefaulted
Docker-internal test cache, and the existing 16-triple writer bound. Prefaulting
is fixture preparation and does not stand in for camera acquisition/alignment.

The first strict 40-second real-image run produced 1,196 accepted groups from
1,197 decisions, but a repeated full-load attempt failed (1,188/1,196, 72 ms first
anchor and up to 134 ms producer lateness). The latter remains FAIL. A complete
20-episode performance acceptance cannot be inferred from the single pass.
Its independently decoded 460 MB file contains roughly 431 MB lossless depth
and 20 MB RGB payload; noisy aligned depth dominates local storage cost.

## Evidence and delivery

- Current scope and node results: [offline completion](offline-completion.md).
- M04 implementation and physical limitations: [leader integration](../m04-gello-adapter/hardware-integration.md).
- New N5 interfaces: [M14](../m14-digital-twin/plan.md), [M15](../m15-dagger/plan.md).
- Historical physical camera layout: [layout recheck](layout-recheck-20260910.md).
- Latest prior lab closeout: [M01 closeout](../m01-runtime-deployment/closeout-20260911.md).
- Previous simulator control/fault gates: [M06 simulation](../m06-control-motion/simulator-control.md).

The accepted `ur12e-collection:current` remains the lab baseline until the new
candidate's applicable gates pass. N7 records immutable image/source identity,
installed tests, bundle checksums, exact cleanup and the remaining lab commands.
Simulation success never authorizes a physical control connection.
