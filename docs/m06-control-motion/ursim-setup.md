# M06: Official URSim Development Environment

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: environment setup accepted. M06 control implementation and
physical motion acceptance remain pending.

## Alignment and scope

On 2026-09-10 the user explicitly requested official-source URSim download and
Docker Desktop setup for basic teleoperation motion simulation. This authorizes
local simulator setup and simulated motion checks. Gazebo is excluded. The
previously proposed URSim-first environment is now selected; no lab connection,
physical command, GELLO integration or production control adapter is included.

## Sources and version choice

- [UR official setup documentation](https://docs.universal-robots.com/Universal_Robots_ROS_Documentation/jazzy/doc/ur_client_library/doc/setup/ursim_docker.html)
  directly references the vendor's Docker Hub repository.
- [Universal Robots Docker Hub repository](https://hub.docker.com/r/universalrobots/ursim_e-series)
  documents model selection, persistent programs, VNC and controller interfaces.
- Docker Hub returned HTTP 404 for tag `5.22.1`, the physical controller's
  version. Select available `5.22.2` from the same minor series; preserve this
  patch difference explicitly. Do not change the physical controller.
- Pin `universalrobots/ursim_e-series:5.22.2` to
  `sha256:39909bad9a8247980a1c9144da322ff7c4d34db0e89870f4c6b4dabd7c55c95d`.
  Docker Hub lists only `linux/amd64`; Mac Apple Silicon uses emulation.

## Setup and interfaces

1. Pull the official pinned image and inspect its supported models and runtime.
2. Use a separate Compose project and dedicated Docker bridge, without host
   networking, USB devices or lab configuration. Bind browser (6080), Dashboard
   (29999), URScript (30002), and RTDE (30004) ports to `127.0.0.1` only.
3. Select UR12 if this pinned version supports it. Otherwise explicitly record
   the closest available UR10 simulation as a surrogate, not UR12 geometry.
4. Persist simulator programs/settings in dedicated Docker volumes. Preserve
   the vendor entrypoint; do not require ROS, Gazebo or extra URCaps for a basic
   simulator-native motion check. No automatic startup motion or restart policy.
5. Verify controller identity, browser UI, RTDE readback and a bounded simulated
   joint move. Leave the simulator running for the user. Document start/stop,
   persistence and remaining application-control acceptance.

Joint targets use radians in base/shoulder/elbow/wrist1/wrist2/wrist3 order.
The user's HOME target is `[0, -pi/2, -pi/2, -pi/2, pi/2, 0]`; a simulator check
does not accept its physical approach path. Simulated state must never be
represented as a physical measurement.

## Acceptance

| Case | Criterion | Result |
| --- | --- | --- |
| M01-A01.ursim | Pinned official image starts and serves PolyScope locally | PASS |
| M01-A03.ursim | Dedicated program/settings volumes survive replacement | PASS |
| M03-A01.ursim | Simulator software/model and actual joints are readable | PASS |
| M06-A02.ursim-smoke | Bounded simulator-only joint motion reaches its target | PASS; UR only, not dual-arm READY acceptance |
| M06-A01..A04 | Production ownership, both-arm READY, bounds and route rejection | NOT RUN; outside setup scope |

Mac emulation establishes functional availability, not real-time servo timing,
physical clearance, Hand-E behavior or hardware safety.

## Runtime findings

The pinned official image includes `programs.UR12e` and supports `ROBOT_MODEL=UR12`.
Its own entrypoint selects the UR12e serial/safety files and the UR10 control
configuration. Dashboard consequently reports `UR10`; do not reinterpret this
as a failed model selection. Runtime reports `5.22.2.1214876 (Jun 24 2025)`.
The image runs Debian 12 with the vendor root entrypoint; this isolated simulator
is distinct from the non-root Ubuntu 24.04 / Jazzy collector. No privileged mode,
extra capabilities or devices are granted. Its memory limit is 4 GiB, with no
additional swap allowance and no CPU cap.

An initial `internal: true` Docker network did not publish the localhost ports
on this Docker Desktop; HTTP connection failed. A dedicated ordinary bridge
resolved it. All four published ports remain loopback-only. This bridge permits
outbound connectivity; it is not an air gap. No lab endpoint is configured or
contacted. No collector container is started automatically.

Settings inspection identified `/ursim/.polyscope` as the location of remote
mode preferences. Persist it along with `/ursim/.urcontrol`, `/ursim/GUI`,
`/ursim/.urcaps` and `/ursim/programs`. Keep these volumes tied to this image
version; do not reuse the GUI volume across an unreviewed version upgrade.

## Validation results (2026-09-10)

Environment: Apple M5 Mac, Docker Desktop 4.90.0, Engine 29.7.2, Compose 5.5.1;
official amd64 image running under emulation. No physical device or lab SSH was
accessed. Terminal installation preceded any browser interaction.

- Registry digest matched the pinned image; `/ursim/version.sh` and Dashboard
  both identify `5.22.2.1214876`. The built-in UR12e serial is `20245199999`.
- Browser returned HTTP 200 and PolyScope rendered successfully. Local-only
  port bindings were inspected. Compose configuration and `git diff --check`
  passed; production source code was unchanged by this environment increment.
- A disposable client on `ur12e-sim_sim` used the already-installed collector
  image's `ur_rtde 1.6.5` receiver. Before issuing simulator commands it required
  the exact simulator serial, version, normal safety status and remote mode.
  Its endpoint is hardcoded to Docker service `ursim`, with no host argument.
- The motion smoke used explicit Dashboard power-on/brake-release and URScript
  `movej`, not a production control adapter. It reached HOME, base +5 degrees,
  and HOME again at 0.2 rad/s and 0.3 rad/s². Each arrival required joint error
  below 0.001 rad and speed below 0.001 rad/s continuously for one second.
  All three passed with RTDE actual-state evidence. No External Control URCap
  installation was needed for this direct-script check.
- Program bytes and Remote Control enablement preferences survived container
  replacement, verified by SHA-256. Restart restores Local / POWER_OFF; saved
  enablement is not automatic control readiness or motion resumption.
- The first replacement stalled at PolyScope startup (38%); the bounded
  Dashboard readiness check failed. Logs were retained. Restart recovered.
  The final Compose uses fixed hostname `ursim` because controller configuration
  persists a host reference, and checks a real Dashboard version response.
  Two subsequent replacements reached healthy state with the fixed hostname.
  This is observed recovery, not proof of the vendor startup stall's root cause.
- The complete three-target motion smoke passed again after final replacement.
  The handoff leaves URSim running at HOME in Local mode, with the Move tab
  showing the rendered arm and `[0, -90, -90, -90, 90, 0]` joint values.
  Dashboard reports RUNNING / NORMAL; this means the simulated arm is powered,
  not that a motion program is executing. No test client remains connected.

Evidence is in ignored `artifacts/ursim-setup/`: registry responses, image
inspection, initial/final motion traces, persistence hashes and failed-start
logs. Durable source selection, checks and limitations are summarized here;
normal operation does not depend on these disposable files. Use the
[quickstart](ursim-quickstart.md) for reproducible startup and interfaces.

The selected environment is usable for basic controller/motion development.
Production M06/M09 ownership, limits, stop behavior and keyboard lifecycle still
need their own aligned implementation plan and tests. GELLO remains blocked;
Hand-E and camera models are not supplied by this setup. Physical HOME routes
and real-time timing remain NOT RUN. Gazebo is excluded.
