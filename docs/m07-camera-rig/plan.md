# M07: RealSense On-Site Probe

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Module: M07
- Status: implemented / hardware acceptance pending (diagnostic slice)
- Parent: [meta plan](../../meta_plan.md)
- Dependencies: M01 SDK environment; M02 role binding follows observed serials
- Updated: 2026-09-09
- Alignment: the user approved prioritizing on-site camera identity/profile checks and short RGB-D samples while connecting devices on 2026-09-09.

## Scope and interfaces

Add an explicit `devices cameras` command, separate from `shadow` and all motion entrypoints. Default invocation enumerates devices and available 640x480@30 profiles without starting streams. `--seconds N --output DIR` explicitly starts a bounded diagnostic capture. Optional repeated `--serial` selects particular devices; otherwise inspect all connected RealSense devices. This diagnostic may inspect a partial rig and must never call that a complete collection rig.

One supervisor owns independent camera workers without blocking one camera on another. Configure RGB8 and Z16 at 640x480@30 and perform SDK depth-to-color alignment. Preserve original color/depth timestamps, domains, frame counters, host monotonic receipt times, depth scale, intrinsics, and USB/firmware identity in JSON/JSONL. Save one selected RGB PNG and one uint16 depth PNG per device, with a pixel-exact depth decode check. Never assign left/right roles from discovery order.

Implementation refinement after the first concurrent run: move native acquisition/alignment into one spawned process per camera. The initial thread workers reported 9-10 color counter gaps per camera in 10 seconds even though each third-view camera passed alone. Process isolation tests whether shared interpreter execution contributes to contention; it is not evidence of a USB fault. Bound native startup/read/cleanup stalls in the supervisor and preserve failed worker reports. Compare the same wiring and SDK before extending the capture to 40 seconds. This remains within the aligned diagnostic slice, not a persistent session implementation.

The frame logs located every initial color gap at the first measured transition. Process isolation reduced but did not remove this startup effect. Warm-up now exercises the complete alignment/copy path before timing begins, rather than only draining raw framesets. Track color gaps, depth gaps, and repeated depth counters independently: an SDK frameset can associate a new color frame with an already observed depth frame. A completed diagnostic (`state=passed`) means acquisition and sample verification completed; it is not a loss-free rate acceptance assertion.

Use the SDK's existing kernel/userspace path first. Do not upgrade firmware, reset cameras, or patch the host kernel. A diagnostic container may map the USB bus explicitly and run with the access needed for this isolated camera probe; it must not mount credentials or use privileged mode. Production non-root udev rules and persistent camera ownership require separate validation.

## Acceptance and implementation

1. Implement enumeration and bounded capture with guaranteed pipeline cleanup and explicit errors.
2. Test orchestration failures with fixtures; run the probe on Ubuntu when cameras are attached.
3. Record actual rates, alignment shape, timestamps, depth equality, faults, and missing devices. Keep footage/serials in ignored local artifacts or on the station.

| Case | Criterion | Environment |
| --- | --- | --- |
| M07-A01.1 | Inventory records real models/serials/firmware/USB; does not invent roles | Ubuntu, no joint motion |
| M07-A02.1 | Bounded capture attempts 640x480 RGB8/Z16 at 30 Hz and reports actual rates for every selected camera | Ubuntu cameras only |
| M07-A03.1 | Aligned uint16 depth, scale, original times and frame IDs preserved; sample PNG is lossless | Ubuntu cameras only |
| M07-A02.2 | Native worker timeout/abrupt exit fails explicitly and bounds process cleanup | Software fixtures |
| M07-A03.2 | Repeated depth is distinguished from new observations and frame counter gaps | Software fixtures |

## Results and remaining work

Software tests pass for cleanup after timeouts, cleanup-error reporting, and exact uint16 PNG round trips. Ubuntu inventory sees a D405 and two D435IF units. The `scripts/camera-probe` launcher maps the USB bus and RealSense video nodes and runs as the non-root operator; USB mapping alone was insufficient for the installed V4L2 SDK backend. No host kernel, firmware, or udev permission changes were made.

Each D435IF passed a separate 10-second 640x480 RGB8/Z16 aligned capture: 300 frames, approximately 29.97 Hz, zero color-frame-counter gaps, and pixel-exact depth PNG decode. One ran over USB 3.2, the other over USB 2.1. These individual tests do not establish three-camera simultaneous throughput. The tested USB 3 depth sample contained approximately 69.7% nonzero pixels; this is scene-specific, not a calibration result.

D405 initially failed with `VIDIOC_S_FMT` / I/O errors while RealSense Viewer held its video nodes. After the user closed Viewer, D405 passed a standalone 10-second run: 300 frames, approximately 29.99 Hz, zero color counter gaps, and exact depth PNG decode. The existing two-Hub wiring was retained throughout.

The first three-camera thread run completed but reported 290/291/290 frames and 10/9/10 color gaps. Every gap occurred at the first measured transition. The process-only comparison gave 300/293/300 frames; adding complete alignment/copy warm-up then produced 1200 frames per camera in a simultaneous 40-second run. RGB and depth both had zero counter gaps and no repeated depth frames. Observed rates were 29.993 Hz for D405 and 29.978 Hz for each D435IF. Maximum host receipt intervals were 33.745, 33.544, and 33.648 ms. All three aligned uint16 sample PNGs decoded exactly. D405 scale was approximately 0.0001 m/unit; D435IF scales were approximately 0.001 m/unit. This is evidence that the current two-Hub and USB 2/3 topology supports this diagnostic workload, without a cable replacement.

The measured 40-second run is `three-camera-warmed-40s-01/` under the probe evidence directory. It used the `84f6067-working-camera-processes` image, recorded by the v3 development bundle. The probe does not continuously encode video or depth, so this result is not M11/M13 storage throughput or the 20-episode acceptance.

Raw inventory, frame timestamps, PNG samples, and reports are under `/var/lib/ur12e-collection/data/probes/`; selected evidence is copied into ignored local `artifacts/hardware/`. Full serials and actual station identity files stay outside Git. Left/right role assignment remains pending user input.

Native capture-worker timeout/exit handling is implemented and fixture-tested. Full three-role session ownership, coordinated interrupt handling, restart handling, and long-lived pipeline acceptance remain pending. This command is not M13 shadow or an episode recorder; no camera synchronization or H.264 throughput claim follows from it.

| Case / execution | Result | Conclusion |
| --- | --- | --- |
| M07-A01.1 / Ubuntu inventory | PASS | D405 plus two D435IF devices identified; roles are not inferred |
| M07-A02.1 / each D435IF separately, 10 s | PASS | 300 aligned frames each, approximately 29.97 Hz, no color counter gaps |
| M07-A02.1 / D405 initial attempts | FAIL | Native stream setup I/O error; Viewer subsequently found holding its nodes |
| M07-A02.1 / all three simultaneously, 40 s after warm-up fix | PASS | 1200 frames per device; no RGB/depth counter gaps or repeated depth |
| M07-A03.1 / both captured D435IF samples | PASS | Original timestamps, depth scale, and exact uint16 PNG preserved |
| M07-A03.1 / all three 40 s samples | PASS | Exact uint16 PNG round trips, original timestamps and per-device depth scale |
| M07-A02.2 / native worker timeout and abrupt exit | PASS | Fixture failures are explicit; bounded cleanup closes pipes and terminates stalled workers |
| M07-A03.2 / source depth accounting | PASS | Fixture distinguishes repeated depth from new frames and counter gaps |

Software validation after this refinement: Black and Pylint pass (10.00/10); 24 tests pass on Mac Python 3.12.13 and in the Ubuntu amd64 development image with ROS Jazzy plugins enabled. Two optional Docker mount tests are skipped in these runs; their earlier explicit pass remains recorded in M01. The Ubuntu run emitted a harmless pytest cache-write warning for read-only `/opt`; all tests completed.

An offline nearest-color-timestamp check of the saved logs found 1198/1200 and 1195/1200 wrist frames within 16.7 ms of each third view. This exploratory calculation permits reuse and includes independently started stream boundaries; it is not the M08 online grouping algorithm, clock validation, or synchronization acceptance. Keep bounded waiting, reuse/eviction, and readiness gating in the separate M08 plan.
