# M09: Operator Collection Entrypoint

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: accepted for offline container delivery / physical acceptance pending,
2026-10-02.
The operator explicitly rejected the host user-local launcher and selected an
interactive container terminal with direct `ur12e gello`, `ur12e cali`, and
related commands. This supersedes the earlier host-entrypoint design below.

## Current scope and interface

- Install `ur12e` as a package console command in the runtime/development images.
  Invoke the existing teleoperation and calibration implementations in-process.
  No Docker executable/socket, host Python environment or source checkout is
  needed inside the container. Keep `ur-collect` and advanced host tools usable.
- An explicit host `scripts/enter.py` command opens the selected local image's
  Bash terminal. It prepares configuration/data mounts, the existing shared
  per-controller lease, image provenance and only required device access. Shell
  entry alone does not initialize SDKs, acquire cameras or start collection.
- The container reads `/config/teleop.ur.json`,
  `/config/recording.station.json` and `/config/task-routes.json`. A missing task
  override uses the image's identity-free task example. Configuration and task
  table overrides remain explicit CLI options. Defaults save under `/data`.
- `ur12e gello` selects a task before hardware initialization, then invokes the
  existing recording owner with operator-started-session semantics. Space HOME /
  start / stop, Hand-E opening, save/discard/quit, watchdogs and timing remain
  unchanged. `dagger` remains unavailable. Calibration motion keeps its existing
  explicit `--operator-approved` requirement.
- Preserve wired-route and bounded packet-loss checks when `gello` starts;
  install `iputils-ping` in the image because these checks previously ran on the
  host. Remove its file capability so the executable works with the retained
  empty capability bounding set; Linux ping sockets use the station's existing
  permitted GID range. Terminal entry/help/menu cancellation does not probe it.
- Translate station-local file paths to the container namespace; preserve the
  original configuration, recordings and old image. Retire the rejected host
  launcher by moving the exact previously installed file into the backup.

## Implementation and acceptance

1. Add the installed console command and direct session/calibration delegation;
   keep help, invalid inputs and menu cancellation free of hardware actions.
2. Share existing Docker restrictions between the advanced host launcher and
   shell entry. Permit explicit Bash through the ROS entrypoint; retain non-root
   execution, required groups, read-only root, bounded memory and shared lease.
3. Update image packaging, station-local path bindings and operator instructions.
   Commit, build from cached dependencies, verify installed files and deploy the
   tested image to the already authorized replacement station.
4. M09-A01: test default/overridden paths, task validation, in-process launch,
   return codes, calibration dispatch, and no nested Docker launch.
5. M01-A01/A03: verify the installed `ur12e` command inside an actual image shell,
   non-root data writes, image provenance, shared lease across containers, no
   Docker socket, unchanged configuration/data and source-free operation.
6. M01-A02: installed offline regression with no network or hardware devices.
   UR/Hand-E/GELLO movement and camera acquisition are NOT RUN in this delivery.

Alignment: the operator's explicit 2026-10-02 correction authorizes this exact
container-terminal interface and replacement of the rejected host launcher.
Technical mount/packaging choices implement that requested interface; no new
control behavior, automatic collection or physical test is authorized.

## Current usage

```sh
# On the station, open the current collector image terminal:
cd ~/ur12e_collection
python3 scripts/enter.py
# Inside the container:
ur12e gello
ur12e gello --output /data/another-dataset
ur12e cali --help
```

The host directory `~/ur12e-data` is mounted as `/data`; station-local files are
mounted read-only as `/config`. Connect the intended leader before entering for
collection. The shell remains available for help when the leader is absent;
re-enter after connecting/re-enumerating devices. Hardware checks remain pending.

## Current results

- M09-A01 PASS on the native Mac: 703 tests passed, five skipped; Black checked
  211 files; production/launcher Pylint passed at 10/10. New checks cover direct
  in-process dispatch, mounted defaults/overrides, calibration/help, wired-route
  failure, cancellation before hardware, terminal mounts and shared lease path.
- M01-A01 PASS: code `d4aabe2` is installed as `ur12e-collection:current`, image
  `afe9aacbb394`, linux/amd64. All 119 installed package/schema files and bundled
  scripts match committed source. Actual image Bash resolves `/opt/venv/bin/ur12e`
  and passes help/menu cancellation without a source checkout, Docker binary or
  Docker socket. Loopback ping passes as UID 1000 with all capabilities dropped;
  the initial candidate's file-capability execution failure was fixed before
  promotion. No robot packet-loss or connectivity test was run.
- M01-A02 PASS for this station's software delivery: installed-image regression
  passed 703 tests with five skips, network disabled, no device mounts, non-root
  execution and read-only root. The final image archive is mirrored to Mac and
  transfer integrity is verified. Logs and receipts are retained in
  `artifacts/container-entrypoint-20261002/`.
- M01-A03 / M09-A01 PASS: the actual host Python 3.10 helper opened an interactive
  current-image terminal and `ur12e` help worked directly. Two installed-image
  instances demonstrated exclusive shared-file lease ownership and subsequent
  release. Non-root data writes and persistence across container replacement
  passed; mounted configuration is read-only and unchanged. Original station
  configuration, recording station and existing recordings are preserved.
- Station-local calibration/evidence paths now use `/config` and `/evidence`;
  the leader calibration and task table are copied into the ignored mounted
  configuration directory. The rejected host wrapper is moved into the backup.
  Previous image/source/configuration are retained at
  `/home/li1013/past_archives/container-entrypoint-20261002-1790891167114310539`
  and tag `ur12e-collection:before-container-cli-20261002`.
- UR/Hand-E/GELLO movement and camera acquisition: NOT RUN.

Historical host-entrypoint acceptance below is retained as historical evidence,
not container acceptance.

## Results, 2026-09-13

- M09-A01 PASS: native full suite 630 passed, 5 skipped; Black and production
  Pylint PASS (10/10). Nine entrypoint cases cover default/relative/spaced/tilde
  paths, help, unavailable DAgger, missing station configuration and exit codes.
  Three existing recording-launcher cases also pass without changed semantics.
- M01-A03 PASS: PC installed-image tests of the mounted host launchers: 12 passed,
  with networking disabled and no hardware device mounts. From `/tmp`, the
  installed symlink displays both help pages. An interactive Bash resolves
  `ur12e` from `~/.local/bin`; its PATH entry is present for new shells. Previous
  `.bashrc` and advanced launcher are backed up in
  `~/past_archives/entrypoint-20260913`.
- Mainline image remains `d3e5186685f3`, with one identity on both hosts; this
  host-only entrypoint does not require a runtime rebuild. The deployment binds
  its current station/configuration files as before.
- Hardware launch via the new shorthand: NOT RUN. No robot/Hand-E/leader controls,
  camera capture or physical preflight were started during implementation.

## Operator-run physical acceptance

The subsequent operator session `1789264560560572282` used the default
`~/ur12e-data` output and completed normally. M09-A01 and the physical shorthand
entrypoint acceptance PASS for this run: five episodes, explicit HOME/start/stop
transitions, three retained outcomes (0000, 0003, 0004), and two intentionally
discarded outcomes (0001, 0002). All five MCAP files remain present; discard is an
explicit dataset disposition, not evidence of a corrupted file.

Independent read-only verification in the PC `current` image passed all RGB
decodes and depth hashes for all five episodes, including discarded ones. Their
durations are 31.425, 3.567, 31.517, 49.550 and 45.551 seconds. Trace
`artifacts/physical-teleop/1789264560559014861/trace.jsonl` contains five stop
requests/acknowledgements and a completed final 30-second hold observation;
the session has no rejection or protective-stop event. This does not resolve the
separately recorded stop-timeout/watchdog edge case from an earlier session.

Verification output is retained locally at
`artifacts/entrypoint-acceptance-20260913/verification.jsonl`. The implementation
was already committed as `6f390e6`; this acceptance update adds the real-run
conclusion without duplicating its implementation commit or starting hardware.
