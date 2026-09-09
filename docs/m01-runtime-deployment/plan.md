# M01: Runtime Architecture and Deployment

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Module: M01 — Runtime architecture and deployment
- Status: implemented / acceptance pending
- Parent: [meta_plan.md](../../meta_plan.md)
- Updated: 2026-09-09
- Dependencies: none; device behavior and episode implementation belong to later modules
- User alignment: host identity and intermittent connectivity confirmed; ROS 2 Jazzy confirmed; implementation kickoff authorized on 2026-09-09 after commit 84f6067

## Problem and Intended Behavior

Provide a reproducible Ubuntu collection environment that colleagues can launch from a delivered image without a source checkout or cloud account. Development must continue on the Mac outside the lab network. The collector must not need an SSH connection from the Mac to operate on the Ubuntu station.

The user-managed alias `ssh ur12e-collection` reaches the collection PC when the lab network is available. It is not the robot controller address. SSH configuration and credentials stay outside the repository, image, and release archive.

## Scope and Non-goals

M01 provides the Python package skeleton, ROS integration boundary, Docker build, Compose profiles, offline delivery bundle, dependency manifest, diagnostic entrypoint, and software-only smoke checks. M01 does not operate joints, enable motor torque, start physical cameras, calibrate devices, or produce accepted demonstration data.

Confirmed on 2026-09-09: use ROS 2 Jazzy for typed messages and observability, retaining direct adapter calls in the future control loop. Final UR driver selection is an M03 decision; M01 must not require either a running UR driver or a robot connection. MCAP plus JSON is the aligned production direction, with codec quality/cost acceptance owned by M11/M13. M01 only supplies the environment.

## Development Configuration

| Item | Configuration and status |
| --- | --- |
| Production target | `linux/amd64`; observed Ubuntu 24.04.3 LTS and Linux `6.17.0-1032-oem` on `ur12e-collection` |
| Host resources | Core Ultra 9 285, 24 logical CPUs, 62 GiB reported RAM, 311 GiB free on root at inspection; capacity snapshot, not throughput acceptance |
| Docker host tools | Docker Engine/CLI 29.4.0 and Compose 5.1.2 verified; user completed Docker group and mount setup |
| Container baseline | Official `ros:jazzy-ros-base-noble` (Ubuntu 24.04 / ROS 2 Jazzy); pin the validated base digest and installed package versions |
| Python | Ubuntu Python 3.12, matching the ROS Python ABI; a virtual environment with access to required ROS system packages |
| Image variants | Production runtime includes installed package and dependencies; development target adds development/test tools |
| Mac checks | Prefer a separately validated `linux/arm64` development target; explicit amd64 emulation is a fallback, with no timing claims |
| Default development backend | Fake inputs, no device nodes, no host networking, no station identities, and no implicit SSH |
| Production persistence | `/var/lib/ur12e-collection` on host maps to `/config`; `/var/lib/ur12e-collection/data` maps to `/data` |
| Station file | Host `/var/lib/ur12e-collection/station.json`, container `/config/station.json`; schema and initialization belong to M02 |
| Runtime privileges | Non-root process with writable mounts; add only required device/group access in the owning hardware module |

The initial device/codec dependency candidates remain those in M01.2 of the meta plan: librealsense 2.56.5, ur_rtde 1.6.5, OpenCV 4.12.0, FFmpeg 7.1.1, PyAV 15.1.0, and optional LeRobot 0.6.1. They are not a validated lockfile. Resolve platform availability and ABI constraints during the build, record exact package versions and hashes, and explicitly revise incompatible candidates. Never claim a pinned FFmpeg executable establishes the versions of libraries linked into PyAV. Use one deliberate OpenCV Python provider with aruco, calib3d, and PNG support.

Keep device and export dependencies in explicit groups. The core fake-device tests must run without loading hardware SDKs or LeRobot. The production image must import its selected hardware and codec dependencies without opening devices. CUDA, Isaac Sim, and model training packages are excluded.

## Design and Interfaces

### Package and command boundary

Use a small `src/ur12e_collection/` Python package, a `pyproject.toml`, and one `ur-collect` command. Separate configuration parsing, environment diagnostics, and CLI dispatch; add device abstractions only in the owning modules. Avoid generic plugin frameworks and speculative adapter implementations.

M01 implements `ur-collect --help`, `ur-collect --version`, and `ur-collect doctor --format json`. Doctor reports package/runtime versions, selected backend, writable mount checks, and missing prerequisites without connecting to hardware or SSH. A machine-readable report has a schema version and explicit available/unavailable/not-checked states. It must not print credentials or arbitrary environment variables.

Reserve the names `station initialize`, `session`, `shadow`, and `calibrate` for later modules. Help identifies them as unavailable until implemented; attempts fail clearly and cannot silently run fake collection. Fake operation must always be explicit in user-facing runtime commands and artifacts. There is no automatic real-to-fake fallback.

### Container and delivery boundary

Use a Dockerfile with development and runtime targets, a Compose file with explicit development and station profiles, and a small launcher. Starting a container displays help or runs the requested command; it must not initialize or move hardware automatically. The station profile may use Linux host networking when device communication requires it. The development profile must not inherit that requirement.

Deliver `image.tar`, checksums, Compose configuration, launcher, sanitized configuration examples, dependency/image manifest, and an English quickstart. The launcher loads or selects an exact local image and does not silently pull a different tag. Network access may be needed to build the release; installing a delivered bundle must work without an image registry. Record image ID, platform, base digest, build revision when available, and resolved dependencies. Unknown source revisions remain explicit.

Persist station configuration and recordings outside the image. Verify permissions before startup and preserve existing files; never overwrite real configuration with examples. Configuration mutation rules belong to M02. Device mappings, udev rules, and any scheduling capabilities are added only when supported by the corresponding hardware plan.

### Intermittent lab connectivity

Normal editing, imports, fake tests, and provisioned container startup must work with SSH unavailable. Remote checks are explicit operations using the SSH alias with noninteractive authentication and a bounded connection timeout. Fail once with a clear result; do not continually reconnect or delay unrelated local tests. Lab disconnection is not an application failure and is not a reason to claim hardware acceptance.

When the host is available, verify Docker daemon access before build/load/run work. Report the current access failure and resolve the deployment access method during implementation; do not silently change groups, socket permissions, host kernel, or the Docker installation. The container uses the host kernel, so RealSense validation must cover the installed OEM kernel. Initial inspection does not justify a kernel replacement.

## Implementation Steps

1. After repository bootstrap and the initial commit, align M01 implementation kickoff on the confirmed ROS 2 Jazzy baseline. Retain later-module decisions as explicit dependencies rather than inventing hardware values.
2. Add the package, CLI, doctor report, and minimal software checks with no hardware imports on the default path.
3. Build the development/runtime images, resolve the selected dependency set, and record actual platform/ABI constraints. Verify imports and codec availability without claiming codec throughput or camera acceptance.
4. Add Compose profiles, mount checks, offline bundle assembly, checksums, and the concise quickstart. Reuse one source of dependency definitions across image targets.
5. Validate locally with unreachable SSH; validate the amd64 release on Ubuntu when accessible and Docker access is resolved. Record unavailable environments as NOT RUN or BLOCKED rather than expanding scope or changing the host spec.
6. Update this plan with commands, actual versions, artifacts, and acceptance conclusions before declaring M01 accepted.

## Acceptance Plan

No M01 acceptance case requires joint motion or physical camera access.

| Case ID | Behavior and pass criterion | Environment | Verification procedure |
| --- | --- | --- | --- |
| M01-A01.1 | Dependencies, help, version, and doctor work; future commands fail explicitly | Development container and Ubuntu amd64 runtime | Import selected dependencies; run CLI smoke cases; check JSON schema and truthful missing-prerequisite results |
| M01-A01.2 | Provisioned local development works without lab SSH | Mac development environment | Run fake checks and CLI with lab access unavailable; assert no SSH invocation or hardware/network connection attempt on these paths |
| M01-A01.3 | Startup has no hardware side effects and no real-to-fake fallback | Software-only | Start each profile with no devices; check default behavior and explicit failures for unavailable runtime commands |
| M01-A02.1 | Delivered bundle runs without source checkout or registry access | Clean Ubuntu 24.04 amd64 machine or VM with Docker | Copy only the bundle, verify checksums, load image, run doctor/help using the launcher with registry access unavailable; record environment cleanliness |
| M01-A02.2 | Runtime works on the actual collection host | `ur12e-collection`, when reachable | Resolve Docker access, load the pinned image, run software-only checks, and record host kernel/runtime/image identity; this does not substitute for the clean-machine case |
| M01-A03.1 | Configuration and data survive container replacement | Container with temporary host mounts | Create distinctive config/data fixtures, remove and recreate container, verify byte-for-byte content and ownership; do not touch real station data |
| M01-A03.2 | Missing/unwritable mounts fail clearly without replacing files | Software-only container | Run against missing and read-only fixture mounts; verify actionable failure and unchanged fixture contents |

## Alignment Record

- 2026-09-09: The user identified `ur12e-collection` as the collection runtime PC and clarified that it is not always reachable during development outside the lab network.
- 2026-09-09: The user confirmed ROS 2 Jazzy, suggested an official image, and authorized repository engineering adaptation and local Docker setup followed by an initial commit. The user explicitly placed M01 kickoff alignment after that batch.
- 2026-09-09: The user approved the proposed order and authorized M01 automatic configuration, the M02/M10 minimal foundation, and prioritized read-only station/device checks while physically connecting equipment. The user will execute necessary sudo commands. No motion acceptance is authorized by this foundation scope.

## Implementation and Validation Results

The foundation is implemented: installed CLI/package, official-base Docker runtime/development targets, Compose profiles, explicit no-pull launcher, dependency diagnostics, hashed Python requirements, and a source-free image bundle. M02 supplies draft initialization and validation; M03/M07 supply explicit read-only/camera diagnostics. Session/shadow/calibration remain unavailable, and GELLO reports unavailable rather than fake readiness.

Python requirements pin jsonschema 4.25.1, NumPy 2.2.6, PyAV 15.1.0, OpenCV contrib headless 4.12.0.88, amd64 RealSense 2.56.5.9235, and ur_rtde 1.6.5. Development tooling pins Black 26.5.1, Pylint 4.0.8, and pytest 8.4.2. An initial pytest 9.1.1 container run failed because Jazzy's installed launch_testing plugin uses a removed hook parameter; pinning pytest 8.4.2 resolved it without disabling ROS plugins. No standalone FFmpeg CLI or LeRobot export package is required by this foundation; M11 owns their eventual integration.

All results below are from 2026-09-09. Code was based on commit `84f6067` plus the current foundation working tree; image labels explicitly say `84f6067-working`. The bundle manifest supplies the immutable image ID and full resolved OS/Python package lists. This is a development handoff, not final hardware release acceptance.

| Case | Environment / command | Result | Conclusion |
| --- | --- | --- | --- |
| M01-A01.1 | Mac Python 3.12.13: `scripts/check`; Ubuntu amd64 `scripts/run station doctor --backend hardware --format json --require-mounts` | PASS | Formatting/lint and core tests pass; every selected Ubuntu SDK imports; both mounts writable |
| M01-A01.2 | Docker `--network none` software tests on Mac arm64 and Ubuntu amd64 | PASS | 20 tests passed in each tested development image before the final GELLO-only test addition; no lab connection required |
| M01-A01.3 | Default help / unavailable session tests and explicit doctor startup | PASS | No automatic device initialization, motion, or real-to-fake fallback |
| M01-A02.1-smoke | Fresh bundle directory on existing Ubuntu station: `scripts/load-release`, then pinned-image doctor and station draft validation | PASS | Image loads and runs without a source checkout or registry fetch; checksum validation succeeds |
| M01-A02.1 | Clean Ubuntu machine/VM deployment | NOT RUN | Existing-station source-free smoke is not evidence of a clean-machine installation |
| M01-A02.2 | Actual `ur12e-collection` host, kernel 6.17.0-1032-oem | PASS | User resolved Docker access; non-root launcher and installed amd64 SDK environment work |
| M01-A03.1 | Mac opt-in `tests/test_containers.py` | PASS | Separate container instances preserve configuration and byte-exact fixture data |
| M01-A03.2 | Mac opt-in `tests/test_containers.py` and missing-directory unit test | PASS | Read-only/missing mounts fail without replacing existing files |

After the M07 diagnostic refinement, the local and Ubuntu amd64 software suites each have 24 passing tests and two intentionally skipped opt-in Docker tests; those two Docker tests were also run explicitly and passed. Pylint reports 10.00/10. Device tests and their limitations are recorded in the owning module plans.

## Remaining Work and Acceptance Conclusion

The foundation is usable locally and on the lab station. The initial v2 development bundle is `/home/robot2026fall/ur12e-foundation-bundle-20260909-v2` on the station, copied into ignored local `artifacts/releases/ur12e-foundation-bundle-20260909-v2/` with checksums verified. Its image ID is `sha256:a30df5a2eca1ad3ec7212d0ccd92b0170773409ec2ecfc7a491d3d1d95365400`; the image archive is approximately 466 MB. Both bundled launchers select the manifest image ID; packaging rejects non-amd64 production images. The subsequent camera refinement is delivered in v3, documented below. Full M01 acceptance remains pending a clean Ubuntu deployment case. Hardware ownership, sustained three-camera capture, motion behavior, and full episode writing belong to their respective modules and remain separate acceptance work.

## Initial implementation decisions

### Camera diagnostic refinement bundle (2026-09-09)

The v3 bundle is `/home/robot2026fall/ur12e-foundation-bundle-20260909-v3` on the station. It packages image `sha256:0699d1029bbffd2e5faf3492a598fecd5145fc0299e692f1ef7ccc2ee4277900`, labeled `84f6067-working-camera-processes`. M07 records its simultaneous 40-second three-camera evidence. The bundle includes spawned camera workers, complete alignment warm-up, separate depth counter statistics, and bounded native-worker cleanup shared with the read-only UR probe.

The existing Ubuntu station passed checksum/load, pinned-image hardware doctor with writable mounts, and bundled camera inventory. Its source launcher defaults now point to the tested runtime/development images. The local copy is `artifacts/releases/ur12e-foundation-bundle-20260909-v3/`; the v2 archive remains a historical snapshot and does not contain these camera fixes. Clean-machine deployment and M11/M13 recording throughput are still NOT RUN.

### Foundation choices

- Use a standard-library CLI with JSON diagnostics and explicit unavailable commands. Keep station validation and time/data contracts in their owning modules.
- Pin direct and transitive Python dependencies in hashed requirements generated from `pyproject.toml`; record installed OS packages separately. Python 3.12 is required.
- RealSense 2.56.5.9235 and ur_rtde 1.6.5 provide CPython 3.12 Linux x86_64 wheels, but not equivalent arm64 wheels. The Mac development image excludes those physical SDKs and reports them unavailable; the Ubuntu amd64 image installs them. This does not change the production hardware requirement.
- Add a pure software test suite for CLI failure semantics, mount preservation, configuration validation/atomic replacement, and intent-versus-feedback contracts. No physical device is opened by default.

## Offline M08/M11 development increment

On 2026-09-09, after leaving the lab, the user authorized local M08 matching and M11 encoding/storage work. The hashed runtime/development requirements now include MCAP 1.4.0 and mcap-ros2-support 0.5.7; doctor reports both without opening hardware. Native Mac checks pass 48 tests with three environment-specific skips; the current local arm64 Jazzy development image passes 49 with two opt-in Docker skips. The M11 plan records its exact image identity and results. Lab synchronization, amd64 rebuilding, and deployment are deferred to the next lab session. Existing v2/v3 foundation archives remain historical artifacts and do not contain these changes.


The subsequent review-correction image `ur12e-collection:m08-m11-review` passes
67 local arm64 Jazzy tests; the two host Docker persistence tests also pass.
The M11 correction results record its immutable identity and the native checks.
This supersedes the earlier M08/M11 test image for software validation only;
amd64 production delivery and physical acceptance remain pending.
