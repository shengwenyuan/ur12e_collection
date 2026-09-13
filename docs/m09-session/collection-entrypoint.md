# M09: Operator Collection Entrypoint

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / offline deployment accepted. The operator requested `ur12e gello` as the daily
collection command, an optional output directory, and future room for
`ur12e dagger`. No new configuration format is required.

## Scope and interface

- `ur12e gello` starts the existing physical GELLO recording session using
  `config/teleop.ur.json`, `config/local/recording.station.json`, image
  `ur12e-collection:current`, and task label `gello_collection`.
- Output defaults to `~/ur12e-data`; `--output DIRECTORY` overrides it. The
  existing recorder allocates unique session directories; older data is preserved.
- Configuration resolves from the installed deployment, independent of the
  operator's working directory. Reuse the existing host Docker launcher and its
  network, USB, lease, image pinning, recording and error handling. Do not create
  a second control/session implementation or a shell-command string.
- Typing `ur12e gello` is the explicit operator launch action, equivalent to the
  existing `--operator-approved` launch. It can initialize SDK/tool connections;
  HOME and following remain gated by the existing Space transitions. No extra
  approval prompt is introduced. Help/invalid commands perform no hardware I/O.
- The CLI uses subcommands. `dagger` remains unavailable until its mainline
  implementation is accepted; never alias it to GELLO or run a placeholder.
- Install a user-local executable symlink on the PC, using its current deployment
  pointer. Keep the advanced `scripts/teleop.py` invocation compatible.

## Acceptance

M09-A01: offline launcher tests prove default and overridden output, complete
recording arguments, current image selection, working-directory independence and
unchanged existing launcher behavior. Reject missing station configuration and
unknown modes before invoking the launcher. Preserve interruption/exit behavior by
calling the existing launcher directly, without an extra supervising subprocess.

M01-A03: installed PC entrypoint resolves through `~/ur12e-current` and displays
help from another working directory. Validate parser/command composition with
mocked launch execution only. No physical connection, preflight, camera capture
or robot/leader/gripper control may be started by this delivery.

Future configuration growth can add task/station presets or a mounted config
file when required. This increment changes no MCAP semantics, protection policy,
TCP offset fields or DAgger implementation.

## Installation

On a provisioned PC with `~/ur12e-current` pointing to the deployment:

```sh
mkdir -p ~/.local/bin
ln -s "$HOME/ur12e-current/scripts/ur12e.py" "$HOME/.local/bin/ur12e"
export PATH="$HOME/.local/bin:$PATH"
ur12e --help
```

Use the existing user-local PATH configuration for subsequent shells. The symlink
follows the current deployment pointer; Python resolves the real script location,
so station paths do not depend on the shell's current directory. No sudo or new
Python environment is needed on the already provisioned collection PC. This is a
host launcher update; the collector's installed Python package and runtime image
are unchanged. Advanced launch options remain in `scripts/teleop.py`.

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
