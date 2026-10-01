# M09: Task Routing and HOME Preparation

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / physical acceptance pending, 2026-09-15. The operator authorized Mac development,
offline tests and candidate-image synchronization while PC production continues.
No production selector, running container or hardware may be changed this turn.
Dependencies: M02 configuration, M05 tool worker, M06 HOME, M10 task metadata.

## Scope and interfaces

- Keep `ur12e gello`. Before hardware access, load a UTF-8 JSON object from
  `config/task-routes.json` (override: `--task-routes PATH`), display the
  descriptions and destination names, and select one task by menu number.
- Keys are complete task descriptions; values are unique ASCII directory names
  using letters, digits, hyphens or underscores, starting with a letter/digit.
  No whitespace, separators, traversal, empty entries or duplicate keys/routes.
  Preserve the selected description verbatim as the existing snapshot `task`.
  Store under `<output>/<route>/session-*`; each session retains its description
  independently of later route-file edits. Existing data is not moved.
- Invalid input retries the menu. EOF/Ctrl+C exits before hardware access.
  No route file means an actionable startup error, not a silently invented task.
  The initial operator task is "Pick up the red block and place it inside the
  small box." mapped to `red-block-in-box`.
- On explicit Space HOME, reuse the existing staged gripper command and bounded
  Hand-E worker to request raw POS=0 with existing SPE=32/FOR=32. Arm HOME and
  opening may proceed together. READY requires measured arm arrival and open
  gripper (existing POS tolerance and completed-motion status). Opening has a
  five-second feedback deadline. No activation, reset or leader motor writes.
  Stop/quit still cancel pending tool work without implicitly releasing a grasp.

## Steps and acceptance

1. Update physical HOME policy, dispatch and fake-device checks under M05-A02 /
   M06-A02. Test rejected arm move sends no gripper command, HOME waits for actual
   opening, timeout stops, and cancellation cannot leak a queued close.
2. Extend the shared daily launcher, with M09-A01 checks for description/route
   preservation, invalid JSON, duplicate/traversal values, input retry/cancel,
   working-directory independence and no hardware calls before selection.
3. Run native formatting, lint and regression; build from cached dependencies,
   test the installed candidate image without network/devices, then stage it on
   PC with matching identity. Do not repoint `current` or overwrite live files.
4. After the operator ends production, switch a matching image/config/launcher
   bundle and verify HOME opening plus a routed multi-episode recording session.
   This hardware acceptance is NOT RUN by offline tests.

The stop-budget correction is tracked in [physical recording](physical-recording.md).
Formal scope follows the operator's explicit feature request; menu/path details
were presented during development. The operator supplied the first task and
requested its creation inside this repository.

## Software acceptance, 2026-09-15

Status: implemented / physical acceptance pending.

- M09-A01 PASS: complete description propagation to the existing recording
  launcher, task directory routing, external-table override, selection retry,
  EOF/Ctrl+C cancellation, empty/malformed/duplicate tables and unsafe directory
  rejection. Selection and validation make no hardware calls.
- M05-A02 / M06-A02 PASS offline: HOME requests opening only after accepted arm
  dispatch; measured opening gates READY, a blocked opening times out, and the
  existing stop cancellation clears staged gripper intent. SPE/FOR are unchanged.
- Native Mac Python 3.12: 654 PASS, 5 SKIP. Black checked 196 files; production
  Pylint 10/10. Initial sandbox execution could not allocate POSIX shared memory;
  rerunning with local shared-memory permission passed. Tests retaining the old
  two-second deadline were corrected to the new policy before the final pass.
- Installed Linux/amd64 Jazzy candidate on Mac Docker: 654 PASS, 5 SKIP; no
  network or devices. The only warning concerns the unprivileged pytest cache
  under `/opt`; it does not change test outcomes. All 109 package source/schema
  hashes match the working tree. Wheel build used the offline local cache; the
  image reused the current dependencies with network disabled.
- Candidate: `ur12e-collection:candidate-20260915`, image
  `sha256:917c714247b2a6d440615ef9681366bade6e2b020a260b8498fa6bc73d4ddcbf`.
  Source label `c78f63f70c81-worktree-9863d68b0c90` explicitly identifies an
  uncommitted working-tree build, not a new commit. Source hashes, image/archive
  identity and test logs are retained in `artifacts/candidate-20260915/`.
- Real Hand-E opening, braking with the new budget, and routed physical recording:
  NOT RUN. Do not promote the image/config/launcher while production continues.

## Staged PC delivery

M01-A01/A03 PASS for candidate synchronization: the PC candidate has the same
image identity and archive SHA-256 as Mac. All 224 staged source/config/test
files match the source manifest. Payload lives at
`~/ur12e-staging/candidate-20260915/`; `source/` is a separate candidate tree.
Do not launch it against the old `current` image. Station-local configuration
must be carried into the candidate only during the later operator-approved
switch, together with promotion of the matching image and deployment pointer.

Read-only before/after checks confirm the production `current` image remains
`d3e5186685f3`, the pointer still selects `ur12e-real-teleop`, and physical profile,
station file and daily launcher hashes are unchanged. The same production
container remained running throughout. No PC tests, hardware connections or
control commands were started. The candidate archive was transferred at 8 MiB/s
and loaded without restarting Docker or containers. Production/hardware
acceptance is deferred until the operator finishes collection.

## Post-production promotion, 2026-09-15

The operator confirms production has exited and the robot is powered off, and
explicitly authorizes PC promotion. First run the candidate's installed suite
on Ubuntu without network or device mounts. Preserve station-local configuration,
calibration and all recordings; back up replaced deployment files under
`~/past_archives/` before installing the manifest-verified candidate sources.
Keep the existing deployment path and daily-command symlink. Promote matching
collector image aliases only after source installation, then check installed
package hashes, configuration parsing, task routing and the help/cancel path
without hardware access. Mirror the current aliases on Mac to the same image.
No control, camera acquisition or physical acceptance is authorized by this step.
Promotion results: M01-A01/A03 PASS. Ubuntu installed-image regression passed
654 tests with five skips, with networking disabled and no device mounts.
The manifest-verified source/profile/task table and matching image are now active
at the existing `~/ur12e-real-teleop` deployment. Both Mac and PC aliases `current`,
`physical-teleop` and `native-isaac` select image `917c714247b2`.

Sixteen changed/new deployment files were installed; previous files and the
station-local directory are backed up at `/home/robot2026fall/past_archives/collector-before-20260915-1789414192772831483`.
The old image identity remains recorded for rollback. All 224 deployed manifest
files match the candidate, and station-local file hashes are unchanged.

Post-promotion checks PASS: 109 installed package hashes, physical profile,
station/calibration parsing, four-second budget, HOME opening, task table, and
help/menu cancellation from `/tmp`. Configuration readback uses the host UID/GID,
as the production launcher does; the first diagnostic using the image's default
UID was denied access to the private station file, with permissions unchanged.
No physical factory was called. Robot/Hand-E motion, camera capture and the next
real recording session remain NOT RUN because the robot is powered off.
