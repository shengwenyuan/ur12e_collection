# Development Environment and Repository Bootstrap

Updated: 2026-09-09. This page preserves the initial bootstrap snapshot from before M01 implementation. For current code, image, dependency, and acceptance status, see the [M01 implementation plan](m01-runtime-deployment/plan.md) and [quickstart](m01-runtime-deployment/quickstart.md). The user subsequently authorized and began the foundation work.

## Engineering baseline

Use the [Google-derived local engineering profile](../skills/project-engineering.md). The four copied Google CI/CD skill entrypoints have a local scope override; their reference files remain inherited material. No Google Cloud deployment, Terraform stack, or cloud account has been configured. `.editorconfig` establishes whitespace conventions; `.gitignore` and `.dockerignore` exclude temporary plans, local identities, credentials, environments, and collection output.

All project documentation is English. The [meta plan](../meta_plan.md) owns stable module IDs and product decisions; the [M01 draft](m01-runtime-deployment/plan.md) owns the proposed runtime implementation and acceptance scope.

## Mac Docker setup

Docker Desktop is installed at `/Applications/Docker.app`. The user completed sign-in. Future setup and verification use terminal commands; interactive authentication or privileged operations remain with the user when necessary.

The user CLI links exist under `~/.docker/bin`, and the login-shell profile contains that directory on PATH. An already-running terminal or agent may retain its previous PATH. For the current shell:

```sh
export PATH="$HOME/.docker/bin:$PATH"
docker version
docker compose version
docker buildx version
```

Do not copy Docker credentials into the repository. Do not reset the user's Docker configuration to fix a missing credential helper; include the CLI/helper directory on PATH. Docker Desktop uses the `desktop-linux` context here. Local Docker operations do not require sudo. In a restricted agent sandbox, access to the Docker socket may require tool-level escalation; this is distinct from a broken daemon or missing host privileges.

Observed working environment:

| Component | Actual value |
| --- | --- |
| Mac | Apple M5, 16 GB unified memory |
| Docker Desktop | 4.90.0 (238679) |
| Docker Engine / CLI | 29.7.2 |
| Compose | 5.5.1 |
| Buildx | 0.36.1-desktop.1 |
| Docker Linux VM | arm64, 10 CPUs, approximately 7.75 GiB memory |
| Official ROS image | `ros:jazzy-ros-base-noble` |
| Pulled repository digest | `ros@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4` |
| Tested platform | `linux/arm64` |
| Container OS / Python | Ubuntu 24.04.4 LTS / Python 3.12.3 |

The existing VM resource allocation is adequate for bootstrap and software checks; it has not been tuned for three-camera collection. The production image target remains amd64 and requires its own validation. The observed official-image digest is a bootstrap reference, not a released collector image.

The official tag is listed in the [ROS Docker Official Image documentation](https://hub.docker.com/_/ros). Versioned tags can move; use the recorded digest when reproducing this check:

```sh
docker pull ros:jazzy-ros-base-noble
docker run --rm --network none \
  ros@sha256:2589a8fba5257307857890173c069852c2abf913a0be7970f172478baecb09e4 \
  bash -lc 'python3 --version; python3 -c "import rclpy; from std_msgs.msg import String; print(String(data=\"jazzy-bootstrap-ok\"))"; ros2 --help >/dev/null'
```

Image acquisition needs network access. Once provisioned, this smoke check runs without network, SSH, lab devices, or a source mount. See [Docker's Mac permissions guide](https://docs.docker.com/desktop/setup/install/mac-permission-requirements/) for the distinction between user CLI installation and privileged host options.

## H.264 feasibility probe

A temporary software-only probe ran on Mac using Python 3.12, PyAV 15.1.0, and NumPy 2.2.6. It created three independent libx264 encoders, each with 60 synthetic RGB8 frames at 640x480 and a 30 Hz time base. Settings were `yuv420p`, `preset=veryfast`, `tune=zerolatency`, `crf=23`, `bf=0`, `g=30`, and `repeat-headers=1`. Each stream started with a keyframe and was decoded with a fresh H.264 decoder. All three returned exactly 60 frames with the expected dimensions.

The probe took approximately 0.34 seconds including generated inputs and decoding; encoded sizes were 210,051, 201,853, and 211,310 bytes. These synthetic, sequential, in-memory results establish encoder availability and basic independent decoding only. They do not establish real-scene quality, compression ratio, three-camera sustained concurrency, storage throughput, timestamp correctness, or MCAP replay acceptance. No camera images or robot data were used.

PyAV reported libavcodec 61.19.101 and libavformat 61.7.100; this does not establish an installed FFmpeg CLI version. The production Ubuntu dependency set remains to be built and tested. The planned packet contract follows the [Foxglove H.264 schema](https://docs.foxglove.dev/docs/sdk/schemas/compressed-video): Annex B, one decodable frame per message, parameter sets with keyframes, and no B frames.

## Lab station

Address update, 2026-09-10: the user identifies `10.18.1.106` as the UR12e
controller. ICMP reachability from Mac and the collection PC passed. This does
not validate Dashboard/RTDE, establish gripper communication, or authorize motion.


Connect explicitly with `ssh ur12e-collection` when on the lab network. The alias is optional for local development and is never probed by default. Its resolved address and credentials are not part of the project.

The station inventory is recorded in M01.2 of the meta plan. The previously observed Ubuntu Docker socket permission problem remains unresolved; local Mac success does not fix it. At Ubuntu deployment time, inspect the current account and available Docker access, then present any necessary sudo operation for the user to execute. Do not change socket modes, group membership, Docker versions, or the installed OEM kernel merely as part of documentation bootstrap.

## Bootstrap validation

| Check | Result | Scope |
| --- | --- | --- |
| Local Docker client and server | PASS | Desktop engine reachable; versions recorded above |
| Compose and Buildx | PASS | Both CLI plugins respond |
| Official Jazzy image | PASS | Pulled and inspected on arm64 |
| Network-isolated ROS startup | PASS | Python, `rclpy`, `std_msgs`, and ROS CLI work with `--network none` |
| H.264 software feasibility | PASS | Three synthetic streams independently encoded/decoded; limits described above |
| Collector runtime / M01 acceptance | NOT RUN | No collector implementation or custom release image exists |
| Ubuntu deployment | NOT RUN | Remote Docker access prerequisite remains unresolved |
| Cameras, GELLO, UR, Hand-E, calibration | NOT RUN | No device interaction performed |

A successful bootstrap is sufficient for the initial repository commit. It does not mark M01 or any hardware module accepted.
