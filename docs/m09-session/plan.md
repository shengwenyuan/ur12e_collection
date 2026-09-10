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
