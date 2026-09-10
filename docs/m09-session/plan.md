# M09: Camera Episode Lifecycle

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Status: implemented / full-module acceptance pending
- Alignment: user approved the next camera batch and module sequence on
  2026-09-09; see [M13 plan](../m13-acceptance/plan.md).

Implement idle -> recording -> finalizing -> idle, with terminal failed/closed
states. One owner submits frames and requests boundaries. A bounded asynchronous
finalizer allows M07 draining throughout MCAP validation. M08 is fresh per episode;
pre-boundary receipt timestamps are excluded. Faults abort the current writer and
retain partial data; completed earlier episodes remain untouched. Ctrl+C follows
this same abort/cleanup path in shadow.

Validate multi-episode independence, delayed finalization, invalid transitions,
writer failure propagation and abort without late commitment under M09-A04.
No keyboard leading, ZERO/READY, discard policy or motion acceptance is included;
these require the remaining M06 and M09 alignment. The public `session` command
remains unavailable until real ownership/stop/hold behavior exists.

## Results (2026-09-09)

M09-A04 PASS for the camera slice: recording/finalization transitions, asynchronous
writer errors, stale frame exclusion, independent next episodes and actual
subprocess Ctrl+C were tested. Camera processes remain alive during MCAP decode.
The [M13 results](../m13-acceptance/plan.md#results-2026-09-09) record native,
Jazzy, repeated-episode and deployment evidence. Full keyboard and robot ownership
acceptance remains NOT RUN; the public session command is still unavailable.


The 2026-09-10 [software baseline](../m13-acceptance/software-baseline.md) closes
the tested software slice of this module. Remaining hardware or unimplemented
full-module cases stay open; repeat software checks only for affected changes
or new failures.

## End-of-episode transport correction (2026-09-10)

The aligned [timing diagnosis](../m08-frame-matching/timing-diagnosis.md) found
pre-cutoff SDK receipts arriving after immediate finalization. Shadow now keeps
the acquisition cutoff fixed while draining transport for one matching-wait
budget. `Session.stop` records the logical cutoff and finalization-request time
separately; a pre-cutoff frame arriving after draining explicitly fails instead
of disappearing during finalization. Robot leading/stop behavior is unaffected.

M09-A04 targeted tests cover delayed pre-cutoff admission, exclusion exactly at
the cutoff, bounded drain, invalid cutoffs, late-after-drain failure and continued
nonblocking finalization. The combined M08/M09/M11/M13 target run passed 59 tests
on Mac Python 3.12; Black and Pylint 10.00/10 passed for the changed runtime code.
Physical verification of the correction uses explicit source overlays; the
released baseline image and proposed performance defaults remain separate.

The corrected physical 20 x 40-second batch passed: every episode retains an
exact 40-second receipt window and every in-boundary wrist receipt has one
decision. No over-budget tail fault or cross-episode leakage was observed.
See the [candidate results](../m08-frame-matching/resource-gates.md).

## Read-only integration increment

Read-only observation recording now shares camera receipt boundaries with independently sampled follower feedback, requires both declared devices and rejects action/command records. This does not implement keyboard leading, HOME movement or stop/hold control. See the
[shared plan and results](../m13-acceptance/readonly-integration.md).

## Autonomous simulation-session increment (2026-09-10)

Authorized by the [M01–M13 sprint](../m13-acceptance/simulator-sprint.md).
Implement a hardware-independent lifecycle and a simulator-only composition root.
A persistent readback connection and recorder/camera process survive episodes;
native Home and SDK control have exclusive, explicitly released ownership.
GELLO input is the clearly identified simulation wave source. Hand-E fields stay
missing and its control stays bypassed. Physical session entrypoints remain disabled.

Use a prepare/commit-start handshake: create the writer before permitting following,
then share one monotonic boundary between control records and camera admission.
The recorder runs in a separate process with bounded IPC, independent of the
control watchdog. Stop revokes target production immediately, records its cutoff,
and drains only pre-cutoff camera/feedback receipts before finalization. Control
stop confirmation and deceleration diagnostics are outside the demonstration.
A recorder failure, overflow or stale worker status stops following and fails the
active episode without automatically resuming. Prepare/start failures cannot
leave following without recording.

Space requires 250 ms of input quiet since the previous key event, so terminal
key repeat cannot advance another phase. Ignore Space during preparation, native
Home, stopping and finalization; require a distinct later press. Normal Space
completion does not label task success. `a` during recording requests the same
stop plus discard; in held review state it discards only the latest episode.
Discard preserves verified files with an atomic `outcome.json` marker. Ctrl+C
stops, retains interrupted partial data, and never requests HOME or releases a
gripper. Events and failed outcomes remain inspectable after process shutdown.

M10 adds explicit simulated control context and authority events; independent
verification requires declared source identities, separate intent/sent/actual
records, monotonic provenance, matching boundaries and absent gripper values.
Read-only feedback validation remains strict and mutually exclusive with control.

Acceptance includes repeated actual URSim episodes with three synthetic cameras,
independent MCAP decoding and source checks, exact start/stop admission, ordinary
completion, held discard, active discard, Ctrl+C, worker failure, full queues,
long key repeat and invalid transitions. Target the full 20 x 40-second batch
after short fault cases pass. Physical M09 and GELLO hold acceptance remain NOT RUN.


### Simulation handover and timing findings

SDK teardown measured approximately 1.04 s after a confirmed normal stop. The
recorder requires a 500 ms owner heartbeat while preparing/following, and allows
a bounded 3 s handover only after receiving explicit measured-stop confirmation.
The controller watchdog is unchanged. Finalization is forbidden before this
confirmation; a failed stop cannot race a successful episode commit.

The first 20 x 40-second attempt failed on a frame receipt newer than the loop's
entry time. Camera queue draining can span a fresh receipt; matcher decision time
now comes from the monotonic clock after the drain, without rewriting receipt
provenance. The failed report remains `session-1789024897120568211/report.json`.
The long-batch gate remains pending until a complete rerun passes.

The next long attempt completed one 40-second episode, then a synchronous test
readback blocked status draining long enough to fill a queue with heartbeat
notifications. Worker liveness now uses a coalesced shared monotonic timestamp;
only reliable state transitions use the reply queue. Independent final readback
runs after the active session closes. Synthetic camera scheduling shares a 30 Hz
phase while preserving actual receipt/acquisition timestamps, avoiding accidental
half-frame phase placement as an unrelated source of fixture matching loss.


The emulator subsequently showed 145–176 ms source delivery stalls while measured
capture work itself peaked at 16.5 ms for draining and 1.1 ms for admission.
A four-frame IPC queue covers only about 133 ms at 30 Hz. The explicit simulator
session profile now reserves **eight frames per camera**, captured in the control
snapshot (roughly 37 MiB of bounded RGB-D payload across three queues). Physical
and camera-shadow defaults remain four frames. Matching stays 16.7 ms skew / 75 ms
wait and tail drain, and active control freshness/watchdog limits are unchanged.
Overflow still fails the episode; no drops are hidden or synthetic times altered.
The preceding two 40-second episodes passed with 1201/1200 accepted triples and
zero source gaps. The full batch must pass under the recorded simulator profile.


The eight-frame run completed five episodes and failed while independently
verifying the sixth completed MCAP. The recorder thread shared the camera owner's
Python process; final-file decoding caused up to 290 ms source delivery delay.
Independent verification now runs in its own persistent process, initialized
before cameras. The writer waits for its bounded result, while acquisition keeps
draining. Abort cancels verification and forbids later commit. This isolates the
expensive complete-file check without weakening any verification, matching or
motion gate. The eight-frame simulator budget remains explicit; physical shadow
continues using its previously accepted defaults. Full-batch rerun is pending.


### Accepted functional increment (2026-09-10)

M09-A01/A02/A03 software and actual URSim functional portions PASS: native HOME,
exclusive following, separate Space edges, held and active discard, recorder loss
and SIGINT. Physical GELLO/Hand-E and physical session gates remain NOT RUN.
`session-1789027034744308007/report.json` passes two 40-second episodes with shared
camera slots and an independent verifier. `session-faults-1789027625131763169`
passes active discard, killed recorder, restart and SIGINT. Ordinary SDK release
is approximately 1.04 s; fault release is approximately 0.55 s, after a measured
stop. Neither path requests HOME or creates gripper feedback.

The fault run exposed leaked shared storage after killing its creating recorder;
the session parent now allocates and unlinks slots and shares its abort signal
with all camera producers. A new session in the same container starts successfully.
Only compact frame headers cross IPC; the recorder copies pixels before releasing
a slot. The explicit simulator writer queue holds at most 16 complete triples,
about 74 MiB of raw payload, to absorb bounded drain bursts. Together with eight
slots per camera this remains bounded. Physical/shadow queue defaults are unchanged.

The console is available through `python scripts/sim_control.py console`. The
launcher freezes source/check overlays, hashes them and records the exact source
manifest before starting the isolated container. Later workspace edits cannot
change an active run. The ordinary hardware session CLI still fails closed before
any transport import. Mac checks: 215 PASS / 4 skipped; Ubuntu 24.04/Jazzy amd64
checks: 217 PASS / 2 skipped. Black/Pylint PASS. The new 20 x 40-second batch remains
running; functional acceptance does not claim its long-duration gate has passed.

### Terminal process-group interrupt correction

The real Docker/PTY console exposed a difference from the earlier `os.kill(pid,
SIGINT)` test: terminal Ctrl+C reaches the whole foreground process group. Camera
and verification children raised KeyboardInterrupt during normal shutdown. The UR
stopped, but child cleanup logs were not a clean acceptance. Make the session
parent the sole terminal-interrupt owner; its recording, camera and verification
children ignore SIGINT and exit through the existing abort/stop channels. SIGKILL
and bounded forced-cleanup behavior remain unchanged. Add a real isolated process-
group test with shared memory, then repeat actual URSim terminal start/stop/discard/
Ctrl+C. Retain the failed console evidence rather than calling it clean shutdown.


Full persistent-session gate now PASSes: twenty 40-second episodes, repeated
native HOME/follow/stop/held transitions and final held discard. The independent
current verifier and grouping audit PASS; see the M13 full-batch result. The real
terminal process-group Ctrl+C correction is validated separately below.

The process-group correction now PASSes an isolated real subprocess-group test:
Ctrl+C reaches the parent, child workers exit cooperatively, shared slots are
unlinked, and stderr is empty. Actual Docker terminal HOME/start/active-Ctrl+C
also exits 130 cleanly without Python/worker tracebacks. Its unfinished episode
remains partial (`console-1789030303415277000`), with SDK release 0.551 s. The
preceding terminal run exercised Space stop/held/a discard; its original noisy
Ctrl+C cleanup remains preserved as the failure that triggered this correction.

Final interrupt regression: Mac 242 PASS / 4 skipped, Black/Pylint 10.00/10.
The signal helper cannot alter the main process handler when called directly.
A separate simulator-only readback after terminal interruption reports runtime
STOPPED, normal safety, zero joint speed and zero drift over one second.

## Cancellation race found during M01 consolidation (2026-09-11)

The full installed-image gate reproduced an existing shutdown race: parent Ctrl+C
sets the shared abort event, camera workers exit, and an already-running recorder
read reports a camera exit as an unsolicited fault. Cleanup and memory removal
succeeded, but the strict clean-terminal test correctly failed. Correct only the
classification after explicit parent cancellation: the recorder must still abort
unfinished output and close all resources, without reporting expected teardown
as a fresh fault. Without cancellation, the same source failure must still be
reported. Add deterministic fault/cancel comparison with real partial-writer
cleanup and vary the actual process-group interrupt timing. This is a bounded
acceptance fix within the authorized image consolidation; no physical test or
change to control, codecs, grouping or normal episode success is involved.

The correction treats an already-set parent abort as cancellation while keeping
unrequested failures visible. A real partial writer is closed in both cases;
no cancelled episode becomes complete. Native regression **PASS: 252 tests,
5 environment skips**, including deterministic cancellation/fault comparison and
three real process-group interrupt timings. Black and Pylint 10.00/10 pass.
Final installed-image acceptance is recorded in the M01 consolidation plan.
