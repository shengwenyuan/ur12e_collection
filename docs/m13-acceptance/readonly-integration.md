# Camera Release and Read-Only Follower Recording

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented / offline acceptance passed; new-image lab integration pending. On 2026-09-10 the user approved steps 1-3 of
camera productionization, read-only UR/Hand-E integration, and recording actual
feedback. Stop before control development; discuss URSim/Gazebo afterward.
Primary plan: M13; affected modules M01/M02/M03/M05/M07/M08/M10/M11.

## Scope and hard boundary

No RTDEControl/RTDEIO, URScript, Dashboard program/mode/stop commands, gripper
SET/activation/reset/motion requests, or enabling a controller interface.
Use Dashboard's fixed identity/status query allowlist, RTDE output subscription,
and an explicit Hand-E GET allowlist only. RTDE subscription negotiation is
read-only protocol traffic, never motion or input-register control. If a service
is disabled/unavailable, retain the failure and continue software development;
do not enable it or claim physical feedback acceptance.
GELLO remains unavailable, calibration stays null, and no leader/action or sent
command is fabricated. No ZERO/READY or full session command is added.

## Ordered implementation

1. Promote the validated camera profile: 75 ms matcher wait/tail drain, 1 ms
   empty polling, PNG level 1 with mandatory independent final-file pixel hashes,
   4 GiB container memory with no CPU quota. Keep 16.7 ms skew and bounded queues.
   Resolve station configuration explicitly, snapshot the effective profile,
   and retain readability of old station/episode schema-v1 files. Reject any
   snapshot/runtime mismatch. Build a pinned amd64 runtime without source
   overlays; verify installed sources and a short camera recording.
2. Add persistent read-only feedback acquisition with bounded startup, polling,
   queues, freshness and cleanup. One isolated worker owns each device connection.
   UR uses only output getters; guard multi-getter coherence using the controller
   timestamp. Hand-E uses fixed GET queries and bounded line parsing, preserving
   raw values and per-sample polling intervals. A required source failure ends
   the observation recording; no automatic reconnect/replay or synthetic fill.
   Confirm live identity/readback separately where the existing service permits.
3. Extend M10/M11 with independent UR and Hand-E feedback records and explicit
   source identities/times, six-joint rad values, TCP in base coordinates with
   the controller's active TCP offset, and available auxiliary/raw status fields.
   Preserve each source separately: Hand-E polling is not an atomic robot sample.
   Record host receipt time mapped to Unix for feedback MCAP publish_time; retain
   controller uptime as a distinct source clock without claiming exposure-time
   alignment. Document receipt-based association and staleness; do not interpolate
   or silently replace unknown values. Add an explicit opt-in read-only shadow
   mode, persistent across episodes, with common receipt boundaries and mandatory
   per-enabled-source coverage. Store actual feedback at its sampled rate;
   future training alignment is separate. No action/control topics are emitted.

## Acceptance and delivery

- M01/M02/M08/M10: old config compatibility, effective-profile schema validation,
  snapshot isolation and mismatch rejection; immutable source/image manifest.
- M03-A01/A02 and M05-A01/A02: read allowlists, partial/malformed/oversized replies,
  unavailable services, bounded failures, stale/repeated/restarted timestamps,
  connection cleanup; assert no prohibited interface/import/wire command.
- M10-A01/A02/A03 and M11-A02: independent source clocks and raw values survive
  MCAP round trip; unknown channels remain absent/null; corrupted feedback fails
  verification; boundary/late-tail and per-source coverage tests.
- M13-A01/A04: camera-only and read-only observation recordings clearly differ
  from demonstrations. Faulted/interrupted work stays partial. Use focused
  software/Jazzy tests and short physical smoke; do not repeat accepted long
  camera batches unless a new failure justifies doing so.
- Record actual PASS/FAIL/NOT RUN/BLOCKED results here. Physical tests require
  readback only, never robot/gripper movement or an enabled control program.


## Pause checkpoint (2026-09-10)

The user requested pausing because the lab was closing. No further build,
hardware recording or motion development is authorized by this checkpoint.
Resume the previously aligned steps 1-3 when the user resumes development.
Stop afterward to align control simulation (URSim/Gazebo); neither is installed
or configured by this work.

### Implemented working-tree changes

- Step 1: effective 75 ms wait / 1 ms polling profile, station defaults and
  snapshot consistency checks; legacy snapshots remain readable. Depth encoding
  relies on mandatory full-file pixel-hash verification. Camera launcher adds
  4 GiB memory with swap disabled and no CPU quota.
- Step 2: persistent UR output-only and Hand-E GET-only reader prototypes,
  isolated workers, identity checks, bounded queues and freshness checks.
- Step 3: independent UR/Hand-E records under `follower/state`, source-specific
  kinds/provenance, receipt-mapped Unix publication time, required source
  coverage, and explicit `shadow --read-feedback`. Action/command records are
  forbidden in this observation mode. No control-session entrypoint was enabled.

These changes are uncommitted WIP. They are not the deployed production image
and must not be represented as completed step 1-3 acceptance.

### Actual checks

| Check | Result | Boundary |
| --- | --- | --- |
| Existing regression suite plus capture-profile cases | PASS: 99 tests, 4 environment/opt-in skips | Mac Python 3.12; new feedback failure cases are still missing |
| Formatting and static checks | PASS: Black, Pylint 10.00/10, `git diff --check` | Current source/scripts; no hardware acceptance implied |
| Synthetic read-only integration | PASS: 2 x 0.4 s, both files completed and independently verified | `artifacts/readonly-integration/synthetic-checkpoint-01/`; cameras and feedback are explicitly synthetic |
| UR read-only preflight | PASS for connectivity/readback | 60 RTDE samples plus Dashboard replies; existing deployed diagnostic only |
| Hand-E read-only preflight | PASS for bridge reply syntax | Only `GET POS/PRE/STA/OBJ/FLT/COU`; not proof of live activated-gripper measurements |
| New amd64 image build | NOT RUN | Buildx could not write its activity file outside the workspace sandbox; Docker did not build an image |
| Persistent real UR/Hand-E plus camera recording | NOT RUN | No new runtime deployment or physical integration test |
| Control/motion | NOT RUN / outside scope | No activation, mode change, power/brake, program, stop/hold or motion commands |

UR Dashboard reported serial `20255100083`, software `5.22.1.1214860`, model
string `UR10`, mode `POWER_OFF`, safety `ROBOT_EMERGENCY_STOP`, and remote control
`false`. Retain the reported model string alongside the user's UR12e identity;
resolve model naming separately. RTDE's all-zero joint feedback under power-off
is not proof of a physical ZERO posture or valid powered-joint measurement.
Hand-E replies were `POS 3`, `PRE 000`, `STA 0`, `OBJ 0`, `FLT 00`, `COU 0`.
The service is reachable; activation, register freshness at the physical gripper,
firmware and device identity remain unverified. Production station configuration
was not modified. Raw preflight evidence is in ignored
`artifacts/readonly-integration/`.

### Resume here

1. Review the uncommitted implementation, especially feedback timestamp brackets
   (not an atomic packet guarantee), strict whole-poll socket deadlines, shutdown
   fault reporting and episode boundary coverage. The prototypes need dedicated
   negative tests before release.
2. Add GET/RTDE allowlist tests, malformed/partial/drip-fed replies, stale/repeated
   controller time, process failure/overflow/cleanup, absent required source,
   corrupted feedback records, late tails and action-record rejection cases.
   Recheck no prohibited device-control API can be invoked.
3. Finish release/snapshot provenance and launch packaging for explicit networked
   read-only observation; the camera-only launcher intentionally has no network.
   Build the pinned amd64 image with an authorized Docker buildx cache write,
   run Jazzy checks, package/hash it, and deploy without source overlays.
4. Run a short camera profile regression and then real feedback-plus-camera
   observation smoke while keeping control disabled. Do not require activating
   the robot/gripper to convert readback connectivity into a false acceptance.
5. Update owning module plans and acceptance conclusions, then stop for the
   control-simulation discussion. Existing unrelated planning edits are retained.

## Offline resumption

The user resumed steps 1-3 outside the lab. Do not attempt lab SSH or device
access. Complete software tests, local Jazzy image checks and an offline bundle;
physical integration remains deferred. The proposed single HOME/READY is
tracked in [M06](../m06-control-motion/home-proposal.md); control work remains
outside this increment.

### Runtime smoke failure and bounded correction

The first amd64 runtime observation smoke failed with writer queue overflow,
including an isolated repeat without concurrent image export. The original
four-item queue counted both RGB-D groups and new small feedback batches.
Separate admission budgets in the same ordered writer FIFO: four ordinary
group/event items and at most 64 queued individual feedback records. Keep one
writer, nonblocking submissions, fail-on-overflow and mandatory final verification.
Report both peaks/capacities. This does not enlarge the image backlog or drop
feedback. Add blocked-writer tests for both independent budgets before rebuilding.
The first packaged candidate is retained as failed-smoke evidence, not delivery.

## Offline completion results

Steps 1-3 are implemented at the software level. No lab connection was attempted
during this offline resumption. New-image physical integration is NOT RUN.

| Case | Result |
| --- | --- |
| Native Mac Python 3.12 | PASS: 127 tests; four ROS/opt-in environment skips |
| amd64 Jazzy development container on Mac emulation | PASS: 129 tests; two host-Docker tests skipped inside container |
| Host Docker persistence checks, final runtime | PASS: both tests |
| Black / Pylint / shell syntax / diff whitespace | PASS; Pylint 10.00/10 |
| Corrected standalone runtime observation smoke | PASS: two 2-second synthetic episodes; each has 60 image groups, with 78 and 79 feedback records; all RGB decoded and depth hashes verified |
| Writer queue peaks | Ordinary items 2/4; individual feedback records at most 3/64 |
| Installed source identity | PASS: all 28 Python/JSON package files match the working tree; hashes included in manifest |
| Offline bundle checksums | PASS: every delivered file verified; image archive 474,430,464 bytes |
| New-image physical cameras + UR/Hand-E | NOT RUN: outside lab |
| Control or simulator development | NOT RUN: outside this increment |

Final runtime:
`sha256:7d3fdd1a9a8cc4e71159892f7373d8af2259bc01d79ce6ba3f507d211727f84e`.
Development image:
`sha256:35a6bdc4af438fc8d8a439edf5ef4e070aaed17f43ac39f86757de9528499feb`.
Both are linux/amd64, labeled `e04ec50-working-readonly-v3`. This is explicitly a
working-tree build, not a claim that commit e04ec50 contains these changes.
The pinned Jazzy base and resolved dependency versions are in the manifest and
package inventories. This increment remains uncommitted.

The verified bundle is ignored
`artifacts/releases/ur12e-readonly-bundle-20260910-v3/`, including `READONLY.md`
and the explicit observation launcher. Earlier
`ur12e-readonly-bundle-20260910/` failed standalone runtime smoke and is retained
only as diagnostic evidence; do not deploy it. Both queue-overflow failures and
the corrected smoke are under `artifacts/readonly-integration/`. The successful
runtime smoke ran after tests/build completed and before image export.
A first local checksum attempt used the macOS system Python lacking
`hashlib.file_digest`; rerunning with the repository Python 3.12 verified all
checksums. No image content changed.

These Mac-emulated container checks establish software behavior and packaging,
not native lab timing or physical 30 Hz throughput. The next lab action is a
short smoke with control interfaces still disabled and a separately reviewed
observation configuration. See the [read-only quickstart](readonly-quickstart.md).

The read-only increment stopped at the M06/M09 alignment boundary. Subsequently,
on 2026-09-10 the user selected official URSim installation and basic motion
simulation, explicitly excluding Gazebo. Its setup and results belong to the
[M06 environment plan](../m06-control-motion/ursim-setup.md). Production control
development and physical motion acceptance remain separate.
