# Current Module and Simulator Handoff

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Updated: 2026-09-12. The latest candidate integrates 120 Hz physical leader
reads and 120 Hz URSim host sends with independent 125 Hz feedback. The Ubuntu
read-only camera/leader batch and independent 20 x 40-second audit PASS;
candidate delivery is tracked in [lab load acceptance](lab-load-20260912.md).
No physical UR, Hand-E or leader write was sent. Earlier offline and physical
results keep their original revision and scope.

| Module | Implemented behavior | Current software/simulation evidence | Remaining physical or delivery gate |
| --- | --- | --- | --- |
| M01 | Pinned Ubuntu 24.04 / ROS 2 Jazzy, non-root unified development/runtime image, mounted station/data and offline bundle | Candidate `2e584b8`: 450 native, 453 Mac installed on recheck, and 453 Ubuntu installed tests PASS; first Mac queue overflow retained; `ec64004` remains the lab baseline | PC bundle load and mount doctor PASS; physical gates pending; no automatic promotion |
| M02 | Strict configuration, atomic updates, camera mount and leader assembly identities, versioned activation/invalidation | Bad identity, stale calibration, changed HOME/assembly and failed replacement tests PASS | Confirm real setup identities; no physical calibration attestation is inferred |
| M03 | Read-only UR state; authorized control transport shared through one owner | Existing actual URSim motion/readback and prior lab readback/READY interruption evidence retained | Real coordinated teleoperation and physical disconnect/watchdog acceptance remain open |
| M04 | Persistent 120 Hz Fast Sync Read DYNAMIXEL acquisition; signed calibration; immutable episode delta; conditioned target; injected HOME/HOLD coordinator | Physical 3 Mbps, 1 ms host latency, continuous 120 Hz concurrent camera workload completed; replay/source-fault and stateful motor tests PASS | No physical motor-write transport in this sprint; ID3 cable, torque profiles, supported holding, powered coordinate binding and accuracy remain open |
| M05 | Read-only raw URCap registers; explicit authorized-socket command client; request versus measured feedback | Local wire fixture tests PASS, including bounded acknowledgements and no implicit release | Full shared sessions explicitly bypass Hand-E; live command/contact/retention tests pending |
| M06 | Exclusive native Home/SDK ownership, configured limits, actual stopped handover and fault latch | 120 Hz sends / independent 125 Hz feedback: actual URSim motion, session and corrected eight-fault campaign PASS; earlier intermittent queue overflow retained | Physical HOME route, motion limits, motor support and coordinated arrival require lab validation |
| M07 | Persistent RealSense rig; three recorded RGB-D producer fixtures under tests | Ubuntu three-camera 20 x 40 audit PASS at about 30 fps with zero source gaps | Diagnostic left/right physical labels and absolute clock accuracy remain unvalidated |
| M08 | Wrist anchors, 16.7 ms skew, 75 ms wait/drain, bounded buffers and no accepted reuse | Matching/failure tests PASS; physical 20 x 40 audit PASS: 99.8375% accepted, worst 99.75%; historical Mac replay batch failed after 13 complete files | Mac amd64 long-load stability and full teleoperation recording remain separate open gates |
| M09 | Space HOME/start/stop, held review, `a` discard, Ctrl+C and fault latch; leader coordinator shares this lifecycle | Replay lifecycle and source/recorder/held-leader faults PASS; historical Mac 20 x 40 batch stopped after 13 completed files | Real leader/Hand-E coordination remains pending |
| M10 | Separate raw acquisition, desired intent, conditioned sent target and actual feedback; immutable baseline/calibration; original versus replay clocks | Independent MCAP audits and mutation tests PASS; all 13 final-image completed real-pixel files reverified | Physical sign/scale validation and verified TF publication are separate gates |
| M11 | Streaming H.264/uint16 PNG MCAP; bounded writer; optional three camera encoding and image-verification workers; official v3 RGB/arm export | Codec/corruption/atomic-write tests PASS; real replay round trips exact depth; serial/parallel payloads match | Physical camera/leader resource workload PASS; combined control-session throughput and gripper/depth training projection remain separate |
| M12 | Offline board solver and held-out checks; taught traversal with 2 s stationary capture; parallel leader configuration workflow | Native geometry/config tests PASS; actual URSim 20 checkpoints / 30 synthetic image-readback pairs PASS | Real board geometry, TCP offset, taught routes, visibility and accuracy thresholds remain open |
| M13 | Shadow, isolated actual URSim checks, strict independent episode audit and fault campaigns | 450 native PASS / 5 environment skips; 453 Mac installed PASS / 2 host skips on recheck; physical read-only 20 x 40 audit PASS | Historical Mac replay and initial new queue failures retained; physical control NOT RUN |
| M14 | Verified typed trajectory export and bounded optional observation mailbox | Export from completed MCAP PASS; stalled/full mailbox cannot own or block control | Isaac scene/integration is interface-only future work |
| M15 | Disabled policy interface and explicit future handover requests | Policy cannot issue commands; handover metadata does not grant ownership: PASS | Policy inference and takeover behavior require future alignment |

## Current behavior and resource boundaries

One follower READY/HOME target remains `[0, -90, -90, -90, 90, 0]` degrees.
Each episode binds a new stable leader baseline to that HOME and preserves the
baseline in its authority record. Signed encoder coordinates are not wrapped.
Desired intent and derivative-bounded commands are archived separately; the
conditioner does not claim an explicit jerk limit. Leader acquisition targets
120 Hz; host commands target 120 Hz with independent 125 Hz RTDE feedback.
Physical serial timing and URSim command timing were measured separately;
physical control at the new cadence is not accepted. More than 100 ms without
valid input faults the session.

The leader HOME/HOLD fixture requires measured arrival within two counts for
200 ms. This tests sequencing and refusal behavior, not real motor accuracy.
External failure during leader HOME preparation or travel requests a fresh
current-position HOLD, including when follower cleanup raises. Cross-process
cancellation is a monotonic byte with local polling; killed waiters cannot hold
up a shared condition acknowledgement. Thirty focused recorder-death repetitions
and the eight-case fault suite PASS. Historical 39ad84b final-image watchdog stop times
are 0.447 s (killed process) and 0.251 s (suspended process), with no observed drift.
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
encoding jobs in the recorder process; each codec has one worker. The optional
verifier has three bounded image jobs,
with file order and associations checked by one owner. The MCAP writer
remains single-owned. Control never waits for image encoding. RealSense hardware
defaults remain unchanged. The Mac replay client uses a 5 GiB cap, a prefaulted
Docker-internal test cache, and the existing 16-triple writer bound. Prefaulting
is fixture preparation and does not stand in for camera acquisition/alignment.

The historical 39ad84b Mac real-pixel workload used explicit 30 Hz replay timing
with synthetic 0/4/8 ms view phases; original capture metadata is retained. It completed 13
40-second episodes, then failed at a 114.276 ms leader gap. The 100 ms limit was
unchanged. The completed subset has 15,595/15,600 accepted groups (99.9679%) and
6.000 GB of MCAP, about 461.55 MB per episode. All 13 files independently pass
RGB decoding, depth hashes, metadata and command audits. This is not a 20-episode
pass. The failed fourteenth episode remains partial.

Maximum writer queue was 8/16, queue delay 235.18 ms and replay delivery lateness
201.50 ms. Completed-file finalization no longer exceeded 25 seconds after the
parallel-verification fix. Earlier original-timing boundary loss, host source
gaps and the initial verification timeout remain failed evidence. One earlier
installed Ctrl+C test timed out; 115 diagnostic repeats and subsequent regular
installed suites passed without a cancellation-code or timeout change. Its cause
is unresolved. Ubuntu complete teleoperation and shutdown regression remain explicit gates.

The Mac comparison temporarily reserved CPUs 0-3 for URSim and 4-9 for the
collector; it is not an Ubuntu requirement. The supplied historical PC snapshot
reports 24 CPUs and about 62.25 GiB RAM. Its earlier two read-only 30-second
captures had one queued group at peak, but did not include the present leader
control workload. All ten VM CPUs are available again after the experiment
(explicit 0-9, because Docker ignored empty updates). No physical performance
claim follows from either comparison.


The 2026-09-12 Ubuntu read-only batch (`7028962`) independently passed all twenty
40-second files with 23,956/23,995 accepted anchors, no source gaps, and maximum
writer queue 2/4. Continuous physical leader reads averaged 119.999998 Hz with
10.693 ms maximum gap and 0.255 CPU cores. Sampled combined CPU peaked at
1.707 cores; memory peaked at 1,300.48 MiB under a 4 GiB cap. Mean storage was
453.332 MB per episode, 96.1% lossless depth. Keep hardware encoding serial and
leave CPU affinity unchanged. This workload has a separate leader JSONL trace,
no UR connection and no control records: complete teleoperation remains open.

Candidate `2e584b8` also passes an installed-image six-second URSim session with
180 accepted groups. Initial Mac installed-shadow and integrated fault-campaign
queue overflows remain unexplained despite passing unchanged rechecks; Mac
long-load reliability is not declared accepted. Production speed, acceleration,
freshness and queue bounds were not relaxed.

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
