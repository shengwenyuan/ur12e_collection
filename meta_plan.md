# UR12e + Robotiq Hand-E Collection: Module Plan

Status: prior lab camera/readback and READY-interruption evidence is retained. The 2026-09-11 offline completion sprint adds recorded leader integration, coordinated fake-motor handovers, real RGB-D replay, calibration traversal and twin/policy interfaces. New batch/image acceptance is in progress; full physical acceptance remains pending. The current [module matrix](docs/m13-acceptance/simulator-matrix.md) supersedes historical availability notes below.

Updated: 2026-09-09. Jazzy, keyboard controls, initial camera skew, and the MCAP direction aligned; repository bootstrap precedes M01 implementation.

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Build a local single-arm collection tool: a custom GELLO leader commands one UR12e and its Hand-E gripper while three RealSense cameras capture RGB-D. Each episode is independently committed. The production storage direction is compressed MCAP plus JSON, using standard H.264 encoding for RGB and lossless 16-bit PNG for depth. Real-scene quality, throughput, and storage cost still require shadow validation; LeRobot v3 is a local export target.

This document preserves confirmed requirements, proposed choices, and unresolved questions. A proposal is not an approved implementation or a hardware acceptance result. Detailed development workflow lives in the repository's `plan-module-work` skill; all project documentation and plans are written in English.

## M00. Scope and Module Registry

### M00.1 Hardware and scope

| Device | Count | Role |
| --- | ---: | --- |
| UR12e | 1 | Six-axis follower; user-confirmed controller IP `10.18.1.106` (2026-09-10) |
| Robotiq Hand-E | 1 | Follower gripper; wiring and access path pending |
| Custom GELLO with DYNAMIXEL XL430-W250-T | 1 | Leader with position-control interfaces; assembled-arm load capability pending |
| RealSense D405 | 1 | `wrist` |
| RealSense D435i family; attached units report D435IF | 2 | `third_left` and `third_right`, on either side of the arm base |

The [actual unit inventory](docs/m03-ur-adapter/controller-inventory.md) records
the user-reported UR12e identity, UR Software `5.22.1`, component versions and
installed URCaps (`Remote TCP & Toolpath`, `UR Connect`, `External Control`,
`Robotiq_Grippers`). DHCP is enabled; the pendant displays
`Not connected to network!` despite reported ping reachability. Reconcile this
discrepancy and recheck the current address before robot integration. These are
inventory observations, not motion or Hand-E communication acceptance.

Confirmed scope includes initialization, a single UR READY/HOME, powered positioning of both arms to READY, Space-based simultaneous leading/recording, stopping and holding, separate visual calibration, RGB-D collection, local storage, and Docker delivery. Digital-twin and DAgger interfaces are reserved; their full runtime implementations are outside the first release.

No pedals, cloud storage, bcecmd, BOS, BucketLink, PFS, model training, or full GUI are required. GELLO hardware/firmware development proceeds separately.

Reuse the older tools' station identity management, persistent sessions, exclusive control ownership, atomic episode commitment, and distinction between operator discard and system failure. Inherit Piper's leader-action/follower-observation semantics for one arm. Do not copy CAN topology, four-arm role switching, ARX5 gravity compensation, or Piper's continued following after recording ends. Here, ending an episode revokes leader control.

### M00.2 Stable IDs

IDs identify responsibility, not mandatory execution order. Never renumber or reuse an existing ID. Append new IDs; retain retired IDs with a replacement reference. Use the same ID in formal plan paths, implementation reports, and acceptance cases. A case such as `M04-A01` retains its meaning across revisions.

| ID | Module | Formal plan directory | Integration prerequisites |
| --- | --- | --- | --- |
| M01 | Runtime architecture and deployment | `docs/m01-runtime-deployment/` | None |
| M02 | Station initialization and configuration | `docs/m02-station/` | M01 |
| M03 | UR device adapter | `docs/m03-ur-adapter/` | M01, M02 |
| M04 | GELLO device adapter | `docs/m04-gello-adapter/` | M01, M02 |
| M05 | Hand-E device adapter | `docs/m05-hande-adapter/` | M01, M02 |
| M06 | Control ownership, limits and READY/HOME | `docs/m06-control-motion/` | M03, M04, M05 |
| M07 | RealSense camera rig | `docs/m07-camera-rig/` | M01, M02 |
| M08 | Frame matching and time semantics | `docs/m08-frame-matching/` | M07 |
| M09 | Session, episode and keyboard lifecycle | `docs/m09-session/` | M06, M08, M10, M11 |
| M10 | Data semantics and metadata | `docs/m10-data-contract/` | None |
| M11 | Encoding, storage and dataset export | `docs/m11-storage/` | M08, M10 |
| M12 | Independent visual calibration | `docs/m12-calibration/` | M06, M07 |
| M13 | Shadow diagnostics and release acceptance | `docs/m13-acceptance/` | Camera path: M07, M08, M11; full collection: M09 |
| M14 | Digital-twin interfaces | `docs/m14-digital-twin/` | M10 |
| M15 | DAgger interfaces | `docs/m15-dagger/` | M06, M10 |

These paths are reserved destinations, not claims that detailed plans already exist. Create a module's `plan.md` before implementing it; give later durable features their own descriptive plan in the same directory. Planning, fixtures, and interface stubs can precede integration prerequisites.

## M01. Runtime Architecture and Deployment

Decision status: ROS 2 Jazzy is confirmed on 2026-09-09; prefer the official `ros:jazzy-ros-base-noble` image. Ubuntu is the production platform; Mac Docker is an initial development/test environment.

Detailed development configuration: [M01 plan](docs/m01-runtime-deployment/plan.md), implementation authorized on 2026-09-09 after repository bootstrap; software and deployment checks are tracked in that plan.

### M01.1 Architecture

The original non-ROS proposal reduced dependencies, DDS/QoS configuration, and image transport overhead. It offered no special control-accuracy advantage and would require more custom recording, inspection, and replay infrastructure.

Given potential MCAP storage, existing project experience, DAgger, and simulation integration, use Ubuntu 24.04 with ROS 2 Jazzy. ROS 2 and the episode file format are separate decisions; MCAP can also be used without ROS 2. [Jazzy platforms](https://docs.ros.org/en/jazzy/Installation/Alternatives/Ubuntu-Install-Binary.html), [rosbag2](https://github.com/ros2/rosbag2).

- Use ROS 2 for messages, status, calibration services, transforms, and recording.
- One controller calls device adapters directly. Servo loops never wait for video encoding, storage, or ordinary ROS callbacks.
- One camera source owns all pipelines and performs alignment/matching internally. Preview, policy, and twin consumers do not reopen cameras or create redundant raw-image transport paths.
- Separate encoding from control with bounded queues. ROS 2 does not itself guarantee synchronization, collision avoidance, or hard real-time execution.
- Do not require MoveIt or a complete ros2_control stack in v0.1. Compare the official UR ROS driver with direct RTDE before choosing the device integration.

```text
GELLO read/write adapter <-> ControlArbiter <-> UR / Hand-E adapters
                                  |
                     commands, feedback, authority events
                                  |
RealSense rig -> RGB-D alignment -> wrist-anchored groups -> EpisodeWriter
                                                           `-> MCAP + JSON
                                                               `-> offline LeRobot v3
                     read-only observations -> twin / future policy
```

### M01.2 Host and image baseline

The initial local inspection found a MacBook Air, Apple M5 with 10 CPU cores, 16 GB unified memory, macOS 26.4, and approximately 552 GiB free storage. Docker Desktop is now installed and its local engine is running. See [development environment](docs/development-environment.md) for the bootstrap checks and shell setup. A simultaneous 40-second three-camera diagnostic has now passed on Ubuntu; sustained encoding/storage throughput remains untested. See the M07 plan for evidence and limits.

The production collection PC is reached through the user-managed SSH alias **`ur12e-collection`** (`ssh ur12e-collection`). This is the collection computer. The user confirmed **`10.18.1.106`** as the **UR12e controller address** on 2026-09-10; it is distinct from the collection PC. ICMP reachability passed from Mac and the collection PC; controller identity readback, RTDE and motion acceptance remain separate. Do not hardcode the alias's resolved IP, credentials, or SSH configuration into the repository or image.

The host is intermittently reachable: the developer may be outside the lab network. Local editing, fake-device checks, and previously provisioned development containers must not require SSH, a lab VPN, or physical devices. Remote checks are explicit and bounded; an unavailable host defers Ubuntu/hardware acceptance without blocking independent local work. Dependency downloads for initial setup still require network access. Do not install a background reconnect loop or make remote probing part of normal test startup.

Read-only inspection on 2026-09-09 reached hostname `ur12e-flexlab`: Ubuntu 24.04.3 LTS, x86_64, Linux `6.17.0-1032-oem`, Intel Core Ultra 9 285 with 24 logical CPUs, 62 GiB reported RAM, and 311 GiB available on the 937 GiB root filesystem. Docker CLI reports 29.4.0 and Compose v5.1.2. Docker access was initially denied. The user subsequently added `robot2026fall` to the Docker group and created the host mounts; a new SSH session verified Engine 29.4.0 access and a running amd64 collector container. USB topology reports xHCI roots including 20 Gb/s links, and all three attached cameras passed simultaneous 640x480@30 RGB-D diagnostics with the existing Hub wiring. GPU capabilities and sustained storage/encoding performance remain unverified.

This host is a reasonable candidate for the planned workload; resource inventory alone is not throughput acceptance. Production requirements must not be limited by Mac RAM, encoding throughput, or virtualization performance. No particular GPU is required. Preserve the installed OEM kernel for initial validation; do not downgrade it merely to match an earlier candidate baseline. RealSense compatibility must be tested on this actual kernel.

Mac tests cover builds, fake devices, sample writing, and replay. Physical USB access is a separate compatibility experiment; Docker Desktop USB/IP does not guarantee every device works. Neither Mac success nor failure replaces Ubuntu acceptance. [Docker USB/IP](https://docs.docker.com/desktop/features/usbip/).

| Component | Candidate version or choice |
| --- | --- |
| Production host | Observed Ubuntu 24.04.3 LTS, x86_64, Linux 6.17.0-1032-oem; validate this installed kernel |
| Container | Official `ros:jazzy-ros-base-noble` on Ubuntu 24.04 LTS; pin the validated image digest |
| Docker / Compose | Ubuntu Engine/CLI 29.4.0 / Compose 5.1.2 verified; Mac Desktop Engine 29.7.2 / Compose 5.5.1 verified |
| Python | 3.12 series |
| RealSense | librealsense 2.56.5; matching Python bindings if used |
| UR adapter | SDU Robotics ur_rtde 1.6.5 candidate, using UR RTDE / URScript |
| LeRobot | Package 0.6.1, commit `7e241bd630a3719a56157a497ce5d08f244784f1`; dataset format v3.0 |
| RGB video | FFmpeg 7.1.1 + PyAV 15.1.0 candidates |
| Depth | OpenCV 4.12.0; 16-bit PNG, initial compression level 1 |
| ROS 2 | Jazzy confirmed; matching rosbag2/MCAP package set, exact package versions recorded at release |
| OpenCV | 4.12.0 with aruco/ChArUco and calib3d; avoid conflicting cv2 installations |
| CUDA / Isaac Sim | Not collector dependencies in v0.1 |
| Device firmware and UR software | UR Software `5.22.1` and component versions are user-reported in the actual unit inventory; independent readback and Hand-E firmware remain pending; no automatic updates |

The M01 foundation now pins and validates its runtime SDK dependencies and image identity; its formal plan and bundle manifests record the exact tested versions. MCAP encoding and optional RGB/arm LeRobot export now pass their software gates. The initial hardware environment is installed; full gripper/depth training projection remains separate M11 work. LeRobot 0.6.1 requires Python >=3.12. ur_rtde is an SDU Robotics project, not an official UR SDK. [LeRobot dependencies](https://github.com/huggingface/lerobot/blob/v0.6.1/pyproject.toml), [ur_rtde](https://sdurobotics.gitlab.io/ur_rtde/pages/getting_started/installation.html).

Deliver an image archive, Compose configuration, launcher, identity-free templates, and short instructions. A colleague loads the image and initializes the station without source code or cloud accounts. Persist configuration and data on host mounts. USB/udev, networking, kernel, and scheduling remain host responsibilities; privileged containers do not create hard real-time guarantees.

Target `linux/amd64` production images. Build/validate `linux/arm64` development images separately if needed; emulated x86 tests on Mac do not qualify production timing.

Acceptance targets: `M01-A01` container dependencies and entrypoints work; `M01-A02` a clean Ubuntu station can deploy without source code; `M01-A03` configuration/data survive container replacement.

## M02. Station Initialization and Configuration

Proposed entrypoint: `ur-collect station initialize`.

1. Bind the UR identity/network address, Hand-E channel, GELLO identities, and camera model/serial/role mapping.
2. Verify real feedback and RGB-D streams; record software, firmware, and USB link information.
3. Configure TCP, payload/center of gravity, mounting, joint limits, ZERO, and READY routes.
4. Make independent M12 calibration available; initialization never automatically traverses calibration poses.
5. Track supervised acceptance of ZERO, dual-arm READY, leader engagement, and stopping/holding before enabling collection.

Use one proposed host environment file, `/var/lib/ur12e-collection/station.json`, mounted into the container. Keep real identities outside Git; version only examples and schema. Task descriptions, output locations, and collection settings remain separate from device identity.

Replace configuration atomically; failed initialization preserves the previous valid file. Recheck identities and current health at session startup. All three camera roles are required; do not silently remove a view while recording. Store calibration version and results here, while retaining the calibration observations/report separately.

Acceptance targets: `M02-A01` identity mismatches block startup; `M02-A02` interrupted updates preserve prior configuration; `M02-A03` one configuration model is shared by initialization and collection.

## M03. UR Device Adapter

Own UR connection, actual feedback, health/mode reporting, and the device-specific execution of authorized motion and stopping. Expose these capabilities only through M06 ownership; other modules must not create a second motion writer.

Read actual six-joint positions and available velocity/current/status data. Distinguish flange and configured TCP poses, units, and orientation conventions. Keep source and receipt timestamps rather than replacing them with publication time. UR feedback is not Hand-E feedback.

Select control frequency from the actual interface, PolyScope version, and measurements; RGB-D at 30 Hz does not set servo frequency. Define controller-side timeout behavior for host stalls, disconnection, or process failure. Sending no more packets is not proof of a hold. Protective/emergency stops take precedence; do not promise powered holding after loss of power or protective faults.

UR10e appearance may serve as a visualization placeholder, but motion, calibration, geometry, and safety properties must be verified for the UR12e unit. [UR RTDE guide](https://docs.universal-robots.com/tutorials/communication-protocol-tutorials/rtde-guide.html).

Acceptance targets: `M03-A01` actual state and mode readback; `M03-A02` authorized stop and hold verification; `M03-A03` timeout/disconnection handling without unintended resumption.

## M04. GELLO Device Adapter

Hardware is confirmed as XL430-W250-T. The assembled mechanism, transport, supply, joint ranges, and sustainable load remain to be measured. GELLO hardware and firmware belong to the parallel project and currently block physical integration. Develop explicit interface stubs and fake-device fixtures first; physical readiness must remain unavailable until real validation succeeds. Author code is a reference, not a validated configuration for this unit. [GELLO paper](https://arxiv.org/abs/2309.13037), [author software](https://github.com/wuphilipp/gello_software).

### M04.1 Interface and motor behavior

Expose `read_state()`, `health()`, `move_to(q, limits)`, `hold()`, `stop()`, and application states `READY_POSITION / LEADING_TORQUE_OFF / HOLD`. Include six measured joint angles, raw gripper input, timestamps, sequence, validity, and a versioned mapping of names, signs, offsets, and units. Unknown fields remain unknown. Application-state changes need not change the motor Operating Mode every time.

XL430 separates power from Torque Enable: powered Torque=0 still allows position readback; Torque=1 enables output. It supports position, extended position, velocity, and PWM modes, but not current or current-based position control. Position-mode enabling can fold reported position back to a single turn. Present Load is inferred, not measured torque. [ROBOTIS manual](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/).

| Application state | Behavior | Required condition |
| --- | --- | --- |
| GO_READY / READY_HOLD | Position control, Torque=1; bounded motion to READY and hold | Validate the assembled arm's load and thermal behavior |
| LEADING_TORQUE_OFF | Remain powered, Torque=0; read angles without sending position goals | Operator support or mechanical balancing; gravity remains present |
| STOPPING / HOLD | Revoke UR following, seed a goal from current GELLO position, then enable holding | Never pursue stale READY/previous goals; support the leader through handover |
| Power loss / protective output shutdown | Active position holding unavailable | Mechanical support, balancing, or a brake if no-drop behavior is required |

Use single-turn Position Mode=3 where the mechanical range permits it. A joint requiring multi-turn operation needs separately validated Mode=4 and host-side limits; do not assume single-turn limit registers still protect it.

Before enabling motion, resolve the actual position branch, seed the current pose, set bounded nonzero motion profiles, and verify the handover. Only then command READY when requested. Block UR following if a torque transition or restart makes continuous-angle mapping ambiguous. Disable or exclude goal-update auto-enabling behavior; leading does not write position goals.

The aligned design uses episode-relative arm mapping: configured follower HOME plus the calibrated leader joint delta from one immutable recording-start reference. Verify the follower is stationary at HOME before each episode; never accumulate prior episode targets or re-anchor during an episode. Calibrate signs, ratios, ranges and HOME, but exact leader/follower startup equality is not required. Keep gripper OPEN/CLOSED mapping absolute. Persist baseline and mapping provenance; HOME/HOLD accuracy remains an independent acceptance gate.

### M04.2 Holding and gravity boundary

v0.1 does not implement active gravity compensation. PWM drive, low position gain, output limiting, or continuously following the measured position must not be presented as validated torque control or zero-force teaching. READY/HOLD use powered position control; leading requires human support or mechanical balancing. Hands-off support during leading requires an additional mechanical solution or separately planned control work.

Measure load, supply behavior, temperature, drift, and faults. Do not equate stall torque with sustainable holding capability or disable overload/thermal protection. Register motor IDs, firmware, direction/offsets, ranges, profiles, and output limits.

Provide explicitly labeled fake constant/trajectory/stale/disconnected inputs for software work. Production mode must not allow a fake leader to command real hardware.

Acceptance targets: `M04-A01` powered torque-off readback; `M04-A02` bounded READY and current-position HOLD; `M04-A03` no stale-goal jump or angle-wrap propagation; `M04-A04` load/thermal acceptance and fake-device isolation.

## M05. Hand-E Device Adapter

Expose raw position requests, actual raw position, activation/motion/contact state, current, faults, and other genuinely available registers. Verify register names and units against the unit and protocol; do not normalize or silently convert raw values to meters or force during collection.

Use a server-client integration as the preferred application boundary: one server owns the gripper device connection, and the collector client sends requests and reads actual raw feedback. The server location, implementation, framing, endpoint, startup ownership, and underlying wiring remain to be verified in M05. Use bounded request timeouts and explicit connection health; a reconnect must not replay stale movement requests. The base device interface is RS-485/Modbus RTU; the server may bridge the UR installation or an external converter. Server-client does not imply that Hand-E itself offers an arbitrary TCP protocol. Do not presume a universal TCP port or obtain fictitious gripper feedback from UR joint RTDE. [Hand-E manual](https://assets.robotiq.com/website-assets/support_documents/document/Hand-E_Manual_UniversalRobots_PDF_20220114.pdf).

The [M05 communication research](docs/m05-hande-adapter/communication-notes.md) identifies `10.18.1.106:63352` as a candidate Robotiq URCap bridge, not a confirmed endpoint. The user reports `Robotiq_Grippers` in the installed URCaps list; its version, wiring and read-only responses remain unverified. Hand-E runtime configuration stays unresolved.

Preserve GELLO gripper input separately from the mapped Robotiq command. Never substitute a requested value for missing actual feedback. Initial stop behavior is to retain the current grasp, not release automatically. This remains a proposed default.

Acceptance targets: `M05-A01` raw request/feedback distinction; `M05-A02` health/contact/fault readback; `M05-A03` no unintended release on episode completion.

## M06. Control Ownership, Limits, ZERO and READY

### M06.1 Motion and ownership

Use one application **READY/HOME**, with UR joint angles
`[0, -90, -90, -90, 90, 0]` degrees in base/shoulder/elbow/wrist1/wrist2/wrist3
order. The user confirmed that this exact physical pose is L-shaped with the end
effector vertically downward. The separate all-zero startup waypoint is retired;
no encoder offsets or factory calibration are changed. The generic station draft
keeps its target unset until the physical station is deliberately configured.

The local URSim implementation uses the official PolyScope Home node through
Dashboard with its installed defaults (60 deg/s, 80 deg/s²). Loading/playing a
program is not arrival: verify actual joint position, standstill and program
completion before granting the next owner. Native Home does not depend on a host
heartbeat and may finish after client loss. SDK following has its own watchdog
and exclusive handover. See [control implementation](docs/m06-control-motion/simulator-control.md).
Physical routes, clearance and motion acceptance remain NOT RUN; physical-control
entrypoints are disabled. The user's simulation authorization does not permit
sending a physical robot command.

READY is the common task start posture. GELLO must eventually reach and hold its
mapped corresponding target; one-sided physical readiness is insufficient.
Its positioning/holding hardware remains externally blocked. Simulator fixtures
are isolated and cannot make an unavailable physical leader ready. Returning HOME
never starts recording, and stopping an episode never automatically returns HOME.

All motion has one owner. Native Home and SDK following use mutually exclusive
ownership, with measured release/arrival before handover. Physical GELLO
coordination and any physical script route remain separate acceptance work.

### M06.2 Mandatory bounds

- Enforce configured joint limits on targets and actual states for leading, READY, calibration, and future policy sources. GELLO has its own bounds.
- Preserve the correct angle branch; arbitrary wrapping must not change physical sweep or cable winding.
- Configure speed, acceleration, step size, command freshness, arrival tolerance, and stopping behavior. Values require site acceptance.
- Initially reject out-of-range commands and stop following; do not silently clamp or chase queued targets.
- Validate starting conditions and the swept path of links, tools, cameras, and cables. Joint limits alone do not prevent self/environment collisions.
- READY must lie within the validated configuration; resolve route/limit conflicts explicitly.
- An already out-of-bounds state requires a separate controlled recovery procedure, not an automatically invented route.

These are mandatory software command limits plus applicable UR safety configuration, not new physical stops or a claim of safety certification. The UR READY target is specified above; physical motion routes and bounds still require site verification.

Acceptance targets: `M06-A01` exclusive ownership; `M06-A02` both arms reach and hold READY; `M06-A03` every motion source obeys limits; `M06-A04` invalid start/routes block motion and collection.

## M07. RealSense Camera Rig

One source owns three persistent pipelines, bound by identity to `wrist`, `third_left`, and `third_right`. Do not restart cameras between episodes.

RGB must be 480p; use Piper's concrete `640x480 RGB8` specification. Every RGB and Depth stream is 30 Hz. Use SDK framesets and align Depth to the local RGB plane, producing Z16/16UC1 depth with the actual depth scale. Preserve individual RGB and Depth acquisition timestamps rather than making them equal after spatial alignment. D435i IMU is not required.

Cross-device simultaneous exposure is explicitly waived. D405 lacks a multi-camera hardware sync signal; timestamp mapping and software matching do not change exposure times. [D400 datasheet, section 7.13, printed page 115](https://realsenseai.com/wp-content/uploads/2025/09/Intel-RealSense-D400-Series-Datasheet-October-2025.pdf).

Acceptance targets: `M07-A01` three correctly identified persistent pipelines; `M07-A02` 480p RGB and aligned Depth at configured 30 Hz; `M07-A03` correct depth scale, image channels, and original timestamps.

## M08. Frame Matching and Time Semantics

The [M08 plan](docs/m08-frame-matching/plan.md) records the offline implementation and tests. The original 50 ms wait was superseded by the user-approved camera productionization: 75 ms by default, eight references per role, and no accepted frame reuse. Effective wait/poll/verification settings are captured in each new snapshot.

Use wrist RGB acquisition time as the anchor. In comparable clock domains, select the closest real left and right RGB-D pairs. The initial confirmed threshold is **16.7 ms** (`max_skew_ns=16700000`), applied independently to each third view relative to the wrist anchor. Reject the whole group if either `abs(t_view - t_wrist)` exceeds this threshold or a member is missing. Equality is accepted; this does not impose a 16.7 ms left-to-right span limit. Preserve per-camera RGB/Depth skew and the complete group span.

- Matching can choose frames before or after the anchor. Use a bounded waiting window; matching latency never blocks servo control.
- Only accepted groups enter image storage. Retain rejection reasons, timestamps, and counts. M08/M11 share freshness rules and matching configuration; accepted RGB times advance by at least the current encoder resolution (1000 ns), and depth times strictly increase. Encode images in their selected temporal order.
- Do not consume a color or depth source image in multiple accepted groups. Use the nearest eligible real candidate within the fixed skew; reject when no unused candidate exists. Wait at most the configured receipt budget (75 ms by default) after wrist receipt, retain at most eight references per role, and report expiry/overflow explicitly.
- Keep device timestamps, time domains, monotonic receipt timestamps, frame/group IDs, and robot-state age. Do not subtract unrelated raw clocks or equate ROS publication time with acquisition time.
- Preserve low-bandwidth UR/GELLO/Hand-E state at its actual rate. A camera group does not force every device onto the camera clock. Training projection and future online observations define their own state/action association and freshness policy.
- Rejected groups may reduce accepted frequency below sensor 30 Hz. Report this; do not duplicate images, compress gaps, or invent uniformly sampled `index/fps` timestamps. Training FPS/resampling is a separate decision.

Source discontinuities always raise a typed M08 fault carrying pending-anchor rejections. The future M07 supervisor owns generation allocation/readiness; M09 owns episode failure and M06 stop/hold requests. Explicit recovery never automatically resumes following.

Acceptance targets: `M08-A01` true nearest-frame selection and threshold rejection; `M08-A02` missing/reordered/overflow cases preserve truthful diagnostics; `M08-A03` no fabricated frames or hidden time gaps.

## M09. Session, Episode and Keyboard Lifecycle

Space starts leading and recording together; another Space ends both. Each episode starts with both arms at READY. A separate leading-without-recording preview is not in v0.1 scope.

```text
INITIALIZE -> UR ZERO -> dual-arm GO_READY -> READY_HOLD
READY_HOLD --Space + engagement checks--> LEADING_RECORDING
LEADING_RECORDING --Space--> STOPPING -> FINALIZING -> HOLD
HOLD --Space--> RETURNING -> READY_HOLD
READY_HOLD --next distinct Space--> LEADING_RECORDING
control fault -> BLOCKED, following revoked and applicable stop executed
```

Confirmed controls: **Space** is state-dependent (start at READY, stop during leading, return both arms to READY while holding); **a** discards an episode; **Ctrl+C** exits the collection task. Returning to READY does not automatically start the next episode. Ignore Space while stopping, finalizing, or returning, and require a fresh press after the transition.

Proposed discard scope for M09 alignment: during recording, `a` stops/holds through the same control path and marks the current episode discarded; in HOLD, it discards only the just-finished episode. It never moves either arm or selects an arbitrary older recording. Whether discarded files are quarantined or removed, and the exact review-window boundary, remain M09 decisions. Ctrl+C must revoke control and initiate a bounded controlled shutdown; interrupted recordings must not appear as normally completed demonstrations. Exiting never requests READY or releases the gripper implicitly.

Prepare the writer and a common start boundary before opening leader control. A partial start must not leave unrecorded following active.

The ending Space event closes the demonstration sampling boundary and revokes following, discarding queued goals. Record deceleration/stopping feedback in session diagnostics, not the demonstration interval. File finalization can complete later. Preserve both the Space timestamp and verified stop-completion time.

Holding means the actual posture after controlled deceleration, not an instantaneous freeze while moving. Verify stop latency/displacement and drift. GELLO seeds a hold at its current position; the operator supports it until handover completes. Subsequent leader movement cannot move the UR. Normal completion does not put UR into freedrive, disable it, return it automatically to READY, or implicitly release Hand-E.

Keep device connections across episodes. Do not resume following merely because writing completed. Debounce keyboard events so a held key cannot cross lifecycle boundaries. Keep operator discard, system failure, and task success distinct; whether a normal Space completion implies task success remains open. Writer success alone does not establish task success.

Host sleep, crashes, and network failures require device-side timeout handling, not only Python cleanup callbacks. Shutdown order must preserve control safety independently of storage finalization.

Acceptance targets: `M09-A01` coordinated Space boundaries; `M09-A02` stopped UR and current-position GELLO hold; `M09-A03` persistent sessions and no unintended restart; `M09-A04` honest discard/failure/finalization outcomes.

## M10. Data Semantics and Metadata

Inherit Piper's semantics: action is leader intent; observation is actual follower feedback. Store collection values before training normalization or joint delta transforms.

| Signal | Meaning |
| --- | --- |
| `leader/state` | GELLO measured/teaching input, mapped six-joint targets, raw gripper input, source time |
| `follower/state` | Actual UR joints, explicitly identified TCP/flange pose, Hand-E raw actual position |
| `follower/state_aux` | Actual UR velocity/current/mode/fault data and available Hand-E raw registers |
| `control/command` | Commands actually sent after constraints, separate from leader intent |
| `control/authority` | Active source, transitions, rejection and stopping reasons; reusable by DAgger |
| `camera/frame_set` | Real members, source times, acceptance/rejection reason |

Future single-arm projection is `action=[leader J1..J6, gripper command raw]` and `observation.state=[UR J1..J6, Hand-E position raw]`. Map leader angles into UR coordinates while retaining raw input. Gripper action uses the Robotiq request derived from GELLO input; retain that input separately and document ranges/directions.

Training alignment (2026-09-11): the primary gripper model feature and action
dimension is one normalized closure scalar, with 0 fully open and 1 fully
closed. Collection continues to preserve raw values. Observation closure derives
from actual POS; action closure derives from leader-requested gripper position,
never substituted from actual feedback. Speed, force, current and status remain
auxiliary diagnostics rather than required model dimensions. Preserve validity
and fault information for data selection even when it is not a model input.
Version the direction and endpoint mappings separately for actual and requested
position; observed open/closed extrema from a short test are not automatically
accepted calibration endpoints. The training export implementation remains pending.

Do not replace action with the follower's next state or silently redefine it as filtered/rate-limited executed commands. Preserve differences in `control/command`; training rules later decide eligibility for rejected/limited intervals.

UR joints use rad and pose translation uses meters. Robotiq raw values do not inherit Piper's meter units or `[0, 0.1]` range. Missing feedback is not zero or the last target. Current is not torque; requested speed/force is not measured speed/force. Pose reference frames and rotation conventions are explicit.

MCAP retains exact mapped acquisition time in publish_time and image headers/provenance. Its log_time is a strictly increasing ordering coordinate, max(acquisition_ns, previous_log_ns + 1), so snapshot/group context precedes payloads in both reading orders. It is not measured write time; training and synchronization use retained acquisition fields.

Episode metadata includes task, outcome, device/calibration snapshot, configuration/software versions, per-stream statistics, group acceptance/rejection counts, codec settings, and bytes per modality. Extend schemas without silently changing existing meanings.

Acceptance targets: `M10-A01` leader intent, sent commands and actual feedback stay distinct; `M10-A02` raw gripper values and units are preserved; `M10-A03` timestamps, identities, calibration and schema versions are traceable.

## M11. Encoding, Storage and Dataset Export

### M11.1 Episode container: MCAP direction aligned

Use **`episode.mcap + metadata.json`** as the production direction. On 2026-09-09 the user selected MCAP provided H.264 encoding does not require substantial custom codec development. Existing FFmpeg/PyAV encoding and the documented Foxglove H.264 schema provide that standard path; this is an implementation-feasibility judgment, not measured three-camera acceptance. A bootstrap probe on Mac with PyAV 15.1.0 / libx264 successfully encoded and independently decoded three synthetic 640x480 sequences of 60 frames each; see the [environment record](docs/development-environment.md). This was not a camera, MCAP replay, or sustained throughput test. No custom codec is planned. Preserve local LeRobot v3 export instead of writing two production representations.

Validate the selected encoder's availability, per-episode decodability, real-scene quality, bounded queues, and measured storage cost in M11/M13. If these fail materially, revisit the decision explicitly; do not silently switch format or keep large raw duplicates. H.264 is a codec and MCAP is a container; storage savings primarily come from the encoded payloads.

The [M11 encoding/storage slice](docs/m11-storage/plan.md) writes accepted groups as independent H.264 streams in `foxglove_msgs/msg/CompressedVideo` and PNG depth in `sensor_msgs/msg/CompressedImage`, using ROS 2 CDR MCAP. The official Python serializer supports native Mac validation without rclpy; rosbag2 playback remains a Jazzy deployment check. Store one compressed depth representation, not raw duplicates or a parallel directory of PNG files. [CompressedVideo](https://docs.foxglove.dev/docs/sdk/schemas/compressed-video), [MCAP plugin](https://github.com/ros2/rosbag2/tree/jazzy/rosbag2_storage_mcap).

### M11.2 RGB and file lifecycle

- Use Annex B H.264 without B frames. Start every episode independently with a decodable IDR and parameter sets; never depend on a previous episode's encoder history.
- Preserve acquisition time and frame/group association, not encoding-completion time. Internal color conversion and lossy errors must be checked against RGB8 input/output expectations.
- Choose CRF/bitrate/GOP after comparing real 480p scenes for detail, CPU, latency, seek/replay, and size. No initial AV1 requirement.
- H.264 and PNG already compress images. Initially keep MCAP indexes and omit additional chunk Zstd or whole-file recompression. Do not write all raw RGB first and rewrite a huge episode later.
- Stream through bounded buffers into a partial directory. Flush encoders, check frame/group counts and timestamps, decode beginning/middle/end samples, close every writer, and atomically commit. Failed closing or validation leaves `.partial`, never a seemingly valid episode.
- Provide local offline v3 export from MCAP. Reuse packets/remux where valid; explicitly report cases requiring re-encoding rather than silently recompressing lossy video.
- Validate exported v3 data with official finalization and the pinned loader. A v3 dataset can share shards across episodes; a standalone episode does not exploit all such consolidation benefits. Package version and dataset format version are different. [LeRobot v3](https://huggingface.co/docs/lerobot/lerobot-dataset-v3).
- Everything remains local. No upload, cloud authentication, or Hub account is required.

### M11.3 Depth: decided as lossless 16-bit PNG

Use single-channel uint16 grayscale PNG, independently per frame. This choice prioritizes exact values, mature decoding, and no temporal dependencies; it does not claim better compression than RVL/Zstd.

- Losslessness is relative to the SDK-aligned Z16 input, not reversibility of spatial alignment.
- Use OpenCV 4.12.0 `imencode('.png', CV_16UC1)`, initial compression level 1, and `IMREAD_UNCHANGED` decoding. Adjust compression level only explicitly after shadow measurements. [OpenCV codecs](https://docs.opencv.org/4.12.0/d4/da8/group__imgcodecs.html).
- Preserve all values, including zero. No 8-bit conversion, normalization, pseudocolor, millimeter requantization, distance clipping, or hole filling. Record actual per-camera `depth_scale`; meters equal raw value times scale.
- Candidate ROS packaging is complete PNG bytes inside `sensor_msgs/CompressedImage`, explicitly labeled with uint16/PNG and depth semantics. Preserve timing/group association. Do not store file paths as image payloads.
- If v3 is selected, prove its depth feature and loader compatibility. An ordinary RGB MP4 is not a substitute for uint16 depth.
- Call OpenCV directly rather than adopting an unaudited compressedDepth pipeline: the Jazzy plugin's uint16 path includes `depth_max` filtering, which can clear values. [Jazzy codec source](https://github.com/ros-perception/image_transport_plugins/blob/jazzy/compressed_depth_image_transport/src/codec.cpp).
- Shadow verification compares shape, uint16 type, every pixel, and zero masks; include 0, 65535, and non-millimeter scales. Measure three streams totaling 90 depth frames/s, queue growth, encoding time, and MiB/episode.
- Codec is decided; throughput and compression ratio are not measured. Diagnose performance before proposing a versioned codec change. Never silently fall back to raw or lossy depth.

### M11.4 Storage budget

For three cameras at 640x480, RGB8 + Z16, 30 Hz, accepting every frame:

| Payload estimate | One 40-second episode | 20 episodes |
| --- | ---: | ---: |
| Uncompressed RGB + Depth | 5.53 GB | 110.59 GB |
| Uncompressed Depth alone | 2.21 GB | 44.24 GB |
| RGB H.264 assuming 2-4 Mb/s per camera | 30-60 MB | 0.6-1.2 GB |

These are decimal GB/MB estimates excluding container/metadata overhead, not measurements. The bitrate range is an illustration, not a quality promise. Depth may dominate after RGB compression. Measure PNG savings and total storage/temporary-space cost in shadow before agreeing a per-episode budget.

Acceptance targets: `M11-A01` pixel-exact depth round trip; `M11-A02` independently decodable RGB per episode; `M11-A03` bounded queues and honest atomic commitment; `M11-A04` measured quality/cost and loader/replay validity for the chosen container.

## M12. Independent Visual Calibration

The [M12 development plan](docs/m12-calibration/plan.md) records the two-round workflow aligned on 2026-09-09. The immediate goal is a common world reference and traceable camera extrinsics across episodes. Providing extrinsics to a future VLM prompt is a possible consumer, not a first-release prompt feature or a claim that calibration removes viewpoint changes. Numerical accuracy targets remain open.

Implemented offline entrypoint: `ur-collect calibrate solve|verify|setup|activate`, separate from production episodes. See [offline usage](docs/m12-calibration/offline-usage.md). Scripted physical capture remains pending. The user first teaches key poses and verifies routes, then converts them into a fixed motion script. Both rounds, including the first held-board round, execute by script. M12 consumes capture checkpoints, actual robot pose feedback and images; it does not generate exploratory motion. Script execution must respect M06 exclusive ownership and limits. The script/checkpoint transport remains to be chosen with the lab controller. Keep the existing 20-40-pose overall budget; the split between rounds and held-out validation is not yet agreed. Store pose IDs, joint targets, required waypoints and expected visible cameras; `dwell_s=2.0`.

Check configuration/board/cameras -> enter exclusive calibration motion ownership -> execute the verified script -> verify arrival/stability at each checkpoint -> dwell for two seconds while capturing -> solve and validate -> atomically update environment calibration. Motion time is not part of the dwell. Report invisible boards, stale pose feedback or failed detection rather than accepting missing samples.

Select clear frames with sufficient corners during each dwell. Approximately 60 frames at one pose are candidates, not 60 independent poses. Include varied rotations and coverage, not only translation or one rotation axis.

Round 1: Hand-E grips a printed ChArUco or AprilGrid board while the left/right D435IF cameras remain stationary and observe the scripted motion for eye-to-hand calibration. Use a flat rigid backing, known dimensions/spacing/dictionary/print scale, and a constant board-to-tool attachment throughout the round. Each fixed camera needs sufficient valid observations; simultaneous visibility of both cameras at every pose is not assumed.

Round 2: secure the board independently on the table and move the rigidly mounted D405 through its scripted eye-in-hand poses. The board stays fixed throughout this round. Wrist visibility of the gripper-held board is no longer required, but the tabletop board must still be in focus, sufficiently visible and resolvable by D405 at the selected poses. The board may be relocated between rounds; its world pose must not be assumed unchanged.

The D435IF cameras are frequently repositioned, with millimeter-scale placement differences reported by the user. An unchanged serial number or approximate return to the same mount location does not establish unchanged extrinsics. Repositioning invalidates the affected camera's active extrinsics and requires a fresh fixed-camera calibration before claiming a calibrated setup. Propose reusing wrist-to-flange calibration while its mounting remains unchanged, with a validity check; do not require round 2 solely because a third-view camera moved. Bind each episode to an immutable calibration/configuration snapshot and retain earlier versions. Exact invalidation UI and startup policy remain M02/M09 integration decisions.

Prefer OpenCV 4.12.0 with ChArUco for corner detection, PnP, and hand-eye/robot-world solving. AprilGrid remains possible with the corresponding detector and corner-ID mapping. No full visual-inertial toolkit is needed for this scope. [ChArUco](https://docs.opencv.org/4.12.0/df/d4a/tutorial_charuco_detection.html), [OpenCV calibration](https://docs.opencv.org/4.12.0/d9/d0c/group__calib3d.html). The wrist observability constraint follows from this installation's geometry.

Use RealSense intrinsics, distortion, and depth scale initially; do not redo factory calibration by default. Save transform direction, units, identities, version, reprojection error, independent-pose validation error, and source observations/report. Selected calibration RGB images are lossless. GELLO joint/HOME/direction and gripper-endpoint calibration form a parallel mainline workflow under `ur-collect calibrate`, sharing versioned configuration principles but not the visual solver. M04 owns device mechanics. TCP/payload setup remains a separate device configuration concern.

Acceptance targets: `M12-A05` leader reference/sign/range/endpoint validation and versioned activation; `M12-A01` configuration-driven traversal and two-second stationary capture; `M12-A02` visibility/detection failures are explicit; `M12-A03` geometrically observable solving and independent validation; `M12-A04` failed calibration preserves the prior valid result.

## M13. Shadow Diagnostics and Release Acceptance

The [M13 plan](docs/m13-acceptance/plan.md) and [lab runbook](docs/m13-acceptance/lab-runbook.md) define the implemented `ur-collect shadow` camera batch with synthetic and hardware backends. Run only cameras, matching, encoding, and candidate writers. It does not start UR/GELLO motion control, require joint actions or ZERO/READY, or pretend simulated robot values are production measurements.

Mac fake-device tests can precede Ubuntu integration. On Ubuntu, shadow measures RGB/Depth rates, accepted groups/skew, missing frames, encoding time, memory, queue backlog, lossless depth equality, and storage. Use moving scene objects without robot motion to assess compression quality.

First-release integrated acceptance is **40 seconds per episode, 20 episodes total**, preferably in one session with repeated READY/start/stop/hold transitions. Shadow may initially use the same 40-second x 20-segment schedule. The earlier 150-second/one-hour minimum is superseded; longer stress tests are optional later work.

Run motion and camera throughput acceptance separately. Required behaviors include UR no longer following after Space, GELLO holding its current posture without a stale-goal jump, limits applying to every motion entrypoint, and failures never appearing as accepted data. Numerical tolerances for stopping, drift, missing-stream timeout, synchronization and cost must be agreed before the corresponding hardware acceptance.

Suggested implementation sequence by ID:

1. Align M01/M02/M06/M10/M11 decisions; plan and stub M03-M05 interfaces.
2. Build fake-device integration for M06/M08/M09/M11 on Mac Docker.
3. Validate M07/M08/M11 through M13 camera-only shadow on Ubuntu.
4. Validate M03-M06 motion incrementally; run M12 separately.
5. Accept the complete M09 flow with M13's 20 episodes and M01's clean-station deployment.
6. Keep M14/M15 limited to interfaces until separately planned and aligned.

Acceptance targets: `M13-A01` shadow requires no joint actions; `M13-A02` camera/codec/time/cost report; `M13-A03` 20 complete 40-second episodes; `M13-A04` separate software/hardware results with unrun cases marked honestly.

## M14. Digital-Twin Interfaces

Reserve `TrajectorySink` events for episode start/end, timestamped sent commands, measured feedback, and faults. v0.1 needs only a null sink and local trajectory export.

Retain joint names/order/units, UR base/tool frames, gripper semantics, calibration version, real times, and episode identity. Keep target-command trajectories separate from executed-feedback trajectories.

Simulation uses a bounded asynchronous read-only channel. It cannot acquire robot control or block control/recording. UR10e appearance is only a potential placeholder, not evidence that a UR12e twin is calibrated. Actual Isaac Sim scene, model, and runtime integration are future scope.

Acceptance targets: `M14-A01` traceable commanded/measured trajectory distinction; `M14-A02` absent or stalled sinks cannot affect real control or recording.

## M15. DAgger Interfaces

Reserve `PolicySource`, `ObservationProvider`, explicit human takeover/resume requests, and sparse authority events. Ordinary collection enables only GELLO control.

A future policy must use the same M06 arbiter and bounds, never a second UR writer. Space remains the episode trigger; takeover keys and precise transitions need separate alignment. Model services, transport protocols, action chunks, and automatic resumption are not implemented in v0.1.

Acceptance targets: `M15-A01` disabled policy interfaces cannot command hardware; `M15-A02` authority events can represent future handovers without changing demonstration semantics.

## Open Decisions by Module

| Modules | Next decision |
| --- | --- |
| M01 | Foundation authorized and implemented; complete release acceptance evidence. Ubuntu Docker access is resolved; final UR control integration remains M03 |
| M04 | Register load, supply, transport and joint range; decide whether hands-off leading requires mechanical support |
| M05 | Resolve the preferred server-client endpoint/protocol, device wiring/raw register access, and gripper hold behavior |
| M06, M09 | Define READY targets/routes, success labels, discard review/retention semantics, and shutdown details. Space / a / Ctrl+C controls are confirmed |
| M08 | Skew 16.7 ms, default wait 75 ms, eight-frame buffers and non-reuse confirmed; validate live clock mapping and startup behavior |
| M11 | H.264/PNG MCAP and optional official v3 RGB/arm export are software-tested; full gripper/depth projection and physical task-image export quality remain pending |
| M12 | Two rounds and taught/scripted motion confirmed; resolve board geometry, controller/checkpoint interface, actual pose reference/TCP offset, pose allocation and validation thresholds in the lab |
| M13 | Agree numerical acceptance tolerances without expanding the 40-second x 20-episode requirement |

## Existing Project References

Read-only reference repositories:

- `/Users/shengwenyuan/1011/ARX5-dual-collection`: meta plan, README, station initialization, pre-episode reset, episode runtime, unified D405 source, LeRobot recomposition, and image release plans.
- `/Users/shengwenyuan/1011/piper-dual-collection-unified`: meta plan, README, relay architecture, station initialization, remaining collection work, Session BLOCK/FAIL, topic contract, and dataset semantics.

Where an older meta plan conflicts with a later dedicated plan, use the later document to understand that project's behavior. This project retains its own confirmed requirements.


### Lab deployment status (2026-09-10)

The M01/M07/M08/M09 camera slice/M10/M11/M13 image is now deployed on
`ssh ur12e-collection`. Camera-free validation passed 24 synthetic episodes,
independent RGB/depth verification, native ROS reading/playback, mount persistence
and interrupted-recording cleanup. No cameras are currently enumerated; physical
20 x 40-second acceptance remains pending role binding and connection. See the
[lab acceptance record](docs/m13-acceptance/lab-20260910.md).

The [accepted software baseline](docs/m13-acceptance/software-baseline.md) defines which checks are closed and the remaining physical-camera test scope. Reopen only affected software cases after relevant changes or a new failure.


### Physical camera status (2026-09-10)

Three cameras are connected and real-input recording was exercised. D405 source
stability failed through its two USB extension stages, also without encoding
and with D405 alone. Both D435IF cameras passed 20-second diagnostics. After
bypassing both extenders, D405 solo, three-camera source, and two 40-second
recording comparisons had zero source gaps/repeats. This strongly implicates the
extension connection path. Subsequent timing and bounded tail-drain corrections
passed a complete experimental 20 x 40-second batch: 99.7916% grouping, every
wrist anchor accounted for, all files verified and zero source gaps/repeats.
The [resource/gate configuration](docs/m08-frame-matching/resource-gates.md)
awaits final alignment before production defaults change. Physical third-view positions are still
unconfirmed; production station configuration is unchanged. See the
[physical test record](docs/m13-acceptance/physical-20260910.md).

The [latest wiring recheck](docs/m13-acceptance/layout-recheck-20260910.md) passed
the user-approved six-episode scope with the experimental profile. Both D435IF
links enumerated as USB 2.1; no source gaps or repeats occurred at the required
640x480/30 Hz mode. The user stopped the remaining batch; seven episodes had
completed by shutdown. This does not claim a second full 20-episode pass.


### Offline read-only integration

[Steps 1-3](docs/m13-acceptance/readonly-integration.md) now pass offline
software and amd64 Jazzy checks. `shadow --read-feedback` and the explicit
`observation-shadow` launcher add UR output-only and Hand-E GET-only acquisition;
no control interface, activation or motion command is present. Independent
feedback records retain source time and host receipt, raw registers and modes,
and do not create action/command records. The ordinary writer queue retains four
items; feedback has a separate 64-record admission budget in the same ordered
FIFO. The immutable v3 offline image is packaged with matching source hashes;
new-image lab integration is deferred until access resumes.

### Local control simulator

On 2026-09-10 the user selected the official Universal Robots URSim Docker image
for local basic motion simulation. Gazebo is excluded from this tool's simulation
scope. The [M06 setup plan](docs/m06-control-motion/ursim-setup.md) records the
pinned image, local-only interfaces and checks. Simulator setup does not accept
the production M06/M09 control lifecycle or any physical route.
Official URSim 5.22.2 with its built-in UR12e profile is installed and running in
Mac Docker Desktop. PolyScope, RTDE feedback, HOME / base +5 degrees / HOME
motion and persistent configuration after replacement passed. The physical
controller remains on 5.22.1; no lab device was accessed for this setup.


The [simulator-control increment](docs/m06-control-motion/simulator-control.md)
now implements shared UR motion ownership, limits, source selection, watchdog
and stop/hold checks. URSim complex trajectories and independent kill/stall
checks passed; physical control remains disabled. The native PolyScope Home
node can reuse installation HOME through a dedicated Dashboard-loaded READY
program, and its speed/stop behavior passed URSim checks. Dashboard disconnect
alone does not stop that program; the accepted native Home design lets it finish
without a host watchdog. Exclusive handover, moving-session recording and
keyboard lifecycle now pass URSim checks; physical acceptance remains separate.


## Current simulator sprint status

The [2026-09-10 simulator sprint](docs/m13-acceptance/simulator-sprint.md) and
[module matrix](docs/m13-acceptance/simulator-matrix.md) supersede older
not-yet-implemented status notes where their dated results overlap. Native Home,
UR-only control/session behavior, independent MCAP recording, optional official
LeRobot v3 RGB/arm export, and offline calibration/activation are implemented.
Physical control remains disabled. GELLO, physical Hand-E actuation, physical
calibration capture, calibration services and calibrated TF remain distinct
open work. Optional read-only ROS typed observation now passes Jazzy and URSim
observer-loss tests; no simulator result establishes physical acceptance.


### Unified image deployed to the collection PC (2026-09-11)

`ur12e-collection:current` is synchronized and software-verified on
`ssh ur12e-collection`; use `/home/robot2026fall/ur12e-current` on that PC.
Native installed tests (255), both mount tests and unchanged station config pass.
The UR12e was offline during deployment; no hardware access or control occurred. See the
[deployment record](docs/m13-acceptance/lab-20260911.md). The eight approved early
local image archives were removed; the current and `ur12e-simulator-6e48d82`
rollback archives are retained. Old Docker images were not deleted.


A later explicit read-only check on 2026-09-11 confirms the powered physical UR12e
is Manual/Local with normal safety and a stopped program. Serial matches the
registered unit; 150 diagnostic feedback samples were captured. See the
[M03 live-state record](docs/m03-ur-adapter/live-state-20260911.md). No control
signals or configuration changes were sent; physical control remains prohibited.


### 2026-09-11 lab closeout

The approved M06 cancellation policy confirms all joint speeds at or below
0.01 degree/s for 200 ms of advancing feedback within two seconds of an immediate
stop request. Hold evaluation begins at confirmation, retaining 0.01 degree/s,
0.05-degree drift and 30-second post-SIGINT observation. Both existing controlled
READY-interrupt traces pass the versioned reassessment; original failed audits
are preserved. See `docs/m06-control-motion/ready-interrupt-test.md`.
The robot is powered off; only software checks and image synchronization may
continue. Production control remains disabled; complete READY, GELLO, physical
watchdog/network-loss and emergency-stop acceptance are still pending.

The closeout image from source `ec64004` is deployed on both Mac and collection
PC under `ur12e-collection:current`; the PC bundle selector is
`/home/robot2026fall/ur12e-current`. Installed Jazzy regression: 300 PASS, plus
two host mount checks PASS. Station configuration is unchanged and no collection
container remains running. See `docs/m01-runtime-deployment/closeout-20260911.md`.


### GELLO integration alignment (2026-09-11)

The user approved the six-stage [physical leader / URSim plan](docs/m04-gello-adapter/hardware-integration.md).
The subsequent review selects follower-HOME-anchored episode-relative joint
deltas, superseding absolute-only engagement. Verify HOME/directions/ranges and
persist each immutable episode baseline. Do not accept the historical 1-2 degree
positioning error as the new HOME/HOLD criterion. Leader calibration is a parallel
M12 workflow. Prioritize 1 Mbps on the current U2D2; neither Mac receive latency
nor dock involvement is conclusively diagnosed. Episode-relative mapping and
its failure/baseline tests are implemented as an isolated intent generator;
real-source session integration and MCAP baseline persistence remain pending.
The guarded baud-maintenance tool completed the explicitly approved seven-axis
migrations to 1 Mbps and then the user-requested 3 Mbps with torque off.
Both 60-second position/velocity runs produced 3,751 groups at 62.50 Hz without
communication errors; maximum source gaps were 20.62/21.57 ms. The active bus
is 3 Mbps. The 120 Hz trial target was not met. The isolated 50 Hz minimum
passes. The user selected nominal 60 Hz leader acquisition and deferred higher
rates to Ubuntu; the existing 50 Hz command loop is unchanged. Source-to-control
age and combined-load gates remain open. No motion was sent.
Read-only leader access is authorized. Every motor register write awaits explicit
confirmation. ID3 cable clearance remains unresolved, and the current base/desk/
hand support is not powered-holding acceptance. Physical UR12e control stays
disabled. Read-only communication, offline calibration and removable lab-image
replay preparation are the initial implementation slices.

The 60 Hz continuation adds a persistent read-only worker, immutable latest/history
views, independent bounded recording, fault latching and M12-compatible evidence.
A 30-second isolated slice measured 54.57 Hz and passed the existing 50 Hz minimum;
two loaded read attempts failed and did not reconnect automatically. Disposable
three-view replay now uses the real matcher/encoder/writer with explicit replay
provenance. Native short replay passed, but the 40-second grouping rate and amd64
Mac throughput failed; no full combined acceptance is claimed. The production
GELLO stub remains unavailable. Clock bridging, mixed-source MCAP, shared-session
integration and physical calibration/HOME/HOLD remain open; see the detailed
[M04 record](docs/m04-gello-adapter/hardware-integration.md).

Priority update (2026-09-11): at the user's request, defer multi-camera alignment
and resource-pressure debugging with all existing failures retained. Proceed
first with isolated M12 leader input calibration and M04 per-axis command
acceptance. Begin with passive OPEN/CLOSED and joint-direction observations;
active torque/goal operations need a concrete per-test start confirmation.
Loaded capture failures remain open but do not block passive calibration.


### Offline completion sprint (2026-09-11)

The user authorized the seven-node [offline completion plan](docs/m13-acceptance/offline-completion.md), coherent commits and obsolete-image cleanup. N1-N5 software is implemented with native and actual URSim evidence. No physical UR, Hand-E or leader writes, and no lab SSH are authorized for this sprint. Signed leader calibration schema 3, immutable episode baselines, separate raw intent/conditioned command audit and injected motor coordination replace the earlier unavailable-only simulation path. The physical device factory remains gated.

M12 now includes configuration-bound leader calibration and taught traversal software alongside the visual solver. M14/M15 have bounded read-only trajectory/policy contracts, not Isaac or inference implementation. Recorded RGB-D replay uses the actual matcher/codec/writer and explicit non-contemporaneous provenance. A strict single 40-second real-image run passes, but the repeated full-load attempt fails; retain both facts and the unchanged gates. New batch, image and lab follow-up results are recorded in M13 rather than inherited from earlier synthetic-only acceptance.
