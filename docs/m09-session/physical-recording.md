# M09 Physical Teleoperation Recording Integration

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: draft for alignment, 2026-09-13. Dependencies: M03/M04/M06 physical
control, M07/M08 camera sources/grouping, M10 semantics and M11 persistence.

## Current boundary

The native physical teleop entry explicitly requires recording=false. The
existing Recorder and session lifecycle are implemented and tested, including
URSim recording; CLI physical session currently rejects execution. The accepted
real control loop therefore does not establish simultaneous MCAP recording.
Do not enable it merely by changing a flag or adding a second control owner.

## Proposed minimum scope

Reuse the physical transport, leader input, relative arm/gripper reference,
conditioner, stop owner and persistent camera Recorder. Integrate through one
session owner and immutable episode boundaries. Keep cameras/encoding/writer
work off the motion loop and use bounded delivery; failed required recorder
health revokes following before cleanup. Preserve the current movement profile.

A distinct Space after HOME starts following and recording on one host boundary;
Space stops both, holds UR and preserves the grasp request. HOME does not open
fingers. A discards the episode through the existing disposition contract;
Ctrl+C stops control and leaves interrupted work distinguishable from complete
episodes. No auto-resume or leader motor writes. Save episode MCAP + JSON;
LeRobot conversion remains outside this repository.

Persist raw leader intent, conditioned/sent command, actual UR feedback, raw
Hand-E readback, calibration/reference, configuration and software/image identity
with original timestamps. Commands at 120 Hz and RTDE at 125 Hz stay independent
of 30 Hz RGB-D; never downsample actions to image groups. Distinguish actual
TCP pose from unknown flange transform; active TCP offset readback remains the
explicit M03/M10 TODO, not an assumed zero offset.

## Proposed implementation and acceptance order

1. Software/fake-device integration: one control writer, atomic begin/end,
   source provenance, sample boundaries, gripper mapping, recorder crash/full
   queue/exception propagation, interrupted output and repeated-episode teardown.
2. No-motion camera shadow: verify current three-camera route, RGB 480p/depth
   30 Hz, aligned RGB-D, wrist-anchored real-frame matching at 16.7 ms, codecs,
   storage and resource headroom. Carry forward existing adopted station gates;
   report source gaps, grouping loss and all rejections instead of relaxing them.
3. Operator-started short combined real episode, then 40 seconds: inspect every
   stream, real/sent/desired distinction, command cadence above 30 Hz, camera
   grouping, queue occupancy, CPU/memory, file size and stop latency. Independently
   decode RGB and verify lossless depth plus MCAP/JSON boundary consistency.
4. Repeat episodes with HOME/new baselines, Space stop, discard and Ctrl+C;
   increase toward the agreed 20 x 40-second batch after short runs pass. Hardware
   fault injections and in-motion stopping require separate operator coordination.

M09/M10/M11 combined physical cases are NOT RUN. The draft authorizes no
implementation or hardware control until concrete scope is aligned. A new image
will be required after integration; the existing control-only image remains a
reproducible accepted baseline.
