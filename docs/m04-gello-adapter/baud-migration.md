# M04: U2D2 Baud Migration and Timing

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: baud migration and isolated 50 Hz minimum passed; 100 Hz target open.
Updated: 2026-09-11. Gates: M04-A01 and M01 delivery verification.
Parent: [hardware integration](hardware-integration.md).

The user approved development of this procedure on 2026-09-11, with an explicit
stop before control signals. This increment implements and tests the maintenance
tool using fake transport, and may run its read-only preparation entrypoint.
The user subsequently explicitly confirmed the reviewed operation: change only
Baud Rate on IDs 1..7 to 1 Mbps, then run read-only timing tests. This authorization
does not include torque, position, motion-profile or other register writes.

## Decision and authorization

Prioritize 57600 -> 1000000 baud on the existing U2D2 and seven XL430 devices.
The user identified low baud as a confirmed throughput constraint. No replacement
adapter or dock is required on current evidence. Mac receive latency is a separate
suspect; an intervening dock alone is not evidence that 100 Hz is unattainable.

This is an EEPROM configuration operation, not read-only diagnostics. The user's
standing requirement for confirmation before any motor register write remains
in force. No write, host baud migration, reboot, torque command or motion is
executed by this planning update. Keep the existing read-only adapter unchanged.

## Official support and timing budget

- [U2D2](https://emanual.robotis.com/docs/en/parts/interface/u2d2/#baudrate)
  lists 1000000 bps with zero nominal rate error and recommends lower USB latency
  for high-speed operation. Its latency instructions do not establish a working
  macOS driver configuration.
- [XL430](https://emanual.robotis.com/docs/en/dxl/x/xl430-w250/#baud-rate8)
  defines one-byte EEPROM Baud Rate at address 8: value 1 is 57600, value 3 is
  1000000. EEPROM changes require torque off. Return Delay at address 9 is a
  separate setting; keep it unchanged in the first comparison.
- Current normal seven-position Sync Read: 21 request bytes plus seven 15-byte
  status packets = 126 bytes before any additional stuffing. At 8N1 this is
  1260 serial bits: 21.875 ms at 57600, or 1.260 ms at 1000000. These are wire
  lower bounds excluding turnaround, return delay, USB buffering and scheduling;
  they are not predicted measured rates or limits for every packet layout.
- The measured 16/32 ms steps motivate further Mac investigation. Raising baud
  removes one bottleneck but does not establish 100 Hz if a receive timer remains.
  Do not reuse the failed IOSSDATALAT experiment or copy Linux/Windows settings.

## Bounded implementation and procedure

1. Prepare a separate explicit maintenance command; no mutation from imports,
   diagnostics or normal startup. Allow only a one-byte Baud Rate write with
   values 1/3/5 to confirmed IDs 1..7 for the two named transitions. No broadcast changes, arbitrary register
   interface, auto torque-off or reboot. Test the emitted packets without serial
   hardware before requesting execution confirmation.
2. Preflight host support for the requested rate; record the adapter identity,
   settings and confirmed device table at 57600. Require all seven model/firmware
   identities, Torque Enable=0, no device faults and register 8=1. Abort on an
   inconsistent bus. The leader remains physically supported throughout.
3. After explicit confirmation, change one identified device at a time. Record
   intent durably before its write; switch the host to 1 Mbps and read identity,
   Baud Rate=3 and Torque Enable=0 from that device before continuing. Switch
   back to 57600 for each remaining device. Do not trust an ACK alone or assume
   a missing ACK means the write did not take effect.
4. On any ambiguity, stop further migration and probe only the two known rates
   read-only to classify each ID. Preserve a per-device old/new/unknown journal.
   A mixed-rate bus cannot pass readiness or start the collector. Never blindly
   retry a write. Recovery uses the journal and a separately explicit action;
   do not reset devices or scan/write unrelated registers.
5. At 1 Mbps, verify all seven identities and register values, unchanged torque,
   goals, PID, mode, limits and profiles. Reopen once and repeat readback. Save
   the host configuration only after complete verification, retaining old
   configuration and the migration journal.
6. Run short position-only normal/Fast Sync Read comparisons, followed by 60 s
   isolated and 60 s combined-load tests. Keep the same USB route and return-delay
   values initially, so baud is the deliberate variable. If host buffering
   dominates, investigate a documented Mac driver path separately. A dock bypass
   is an optional controlled comparison if accessible, not a prerequisite.

## Acceptance and current state

Software cases: reject unauthorized registers/IDs/widths; refuse nonzero torque
without changing it; complete seven-device migration; lost ACK with successful
new-rate readback; absent device; partial migration; interruption and journal
recovery; no ready state on mixed/unknown rates. Preserve read-only wire tests.

Transport acceptance stays >=50 fresh complete groups/s minimum, 100 Hz target,
p99 sample gap/age <=40 ms and no >100 ms steady-state gap/age. Report errors,
missing samples, CPU cost and all latency percentiles. Do not manufacture rate
from repeated cached samples or accept a single-device rate as full-arm rate.

## Implementation and read-only preparation results

During authorized execution, two preflight attempts stopped before writes:
ID1 goal/actual changed together by two counts, then ID7 by one count. All IDs
were read-only classified at 57600. Correct the static comparison to retain and
permit a changed goal only when both old/new states have torque off and each goal
equals its concurrent actual position. All other configuration comparisons remain
exact. Independent goal changes, nonzero torque and PID changes still fail tests.
Record the observed preflight inventory before comparison, including failures.
This handles observed inactive-state readback behavior; it does not change any
HOME/HOLD tolerance or authorize goal writes.

Implemented `python -m ur12e_collection.leader.maintenance prepare|apply`.
The apply entry requires a prepared plan and explicit `--confirm-baud-write`;
normal `devices leader` remains read-only. Preparation does not arm writes.
The maintenance port permits one addressed Baud Rate write at a time. Readback
verifies model, firmware, ID, rate and torque. Every write intent is fsynced first;
failures stop further writes and classify IDs at only the two known rates.
Partial/unknown buses never report completion. No automatic rollback, torque
toggle, reboot, motion profile or goal operation exists in the entrypoint.
The verified connection is reported in the result; station configuration is
not silently rewritten. Explicit rollback tooling remains future work.

Software PASS: complete migration/reopen with lost ACKs, rejected nonzero torque,
mixed/absent devices, corrupted prepared plan, partial migration, interruption,
durable-journal failure and no false completion. Real SDK packet-encoding tests
reject wrong register, ID, value and width; unconfirmed apply opens no device.

Read-only physical preparation PASS (2026-09-11): the host accepted 1000000 baud,
then returned to 57600 with unchanged device configuration. Seven XL430 model
1060 / firmware 50 devices report Baud Rate=1, Torque Enable=0 and no faults.
Traffic was exactly 28 READ instructions and zero motor writes. This checks
host configuration support, not successful communication with motors at 1 Mbps.

Prepared operation: `artifacts/gello/baud-plan-1mbps.json`, digest
`31c4bd57f3448a37a9414ddf27f1e904970ce9ef33c75a9a821564f8ae08093b`.
The original prepared command below is retained for history; its preflight
stopped before writes. Do not rerun it on the now-migrated bus:

```sh
.venv/bin/python -m ur12e_collection.leader.maintenance apply \
  --plan artifacts/gello/baud-plan-1mbps.json \
  --output artifacts/gello/baud-apply-1mbps \
  --confirm-baud-write
```

It changes only address 8 from 1 to 3 on IDs 1..7, including ID3's communication
setting; it never moves ID3 or removes its motion interlock. Expected motion is
none. Preflight is repeated immediately before writes. A failure can leave a
mixed-rate bus; use the journal/read-only classification rather than re-running
the same operation blindly. Higher-rate timing acceptance remains NOT RUN;
the original measured baseline was 31.19 Hz at 57600 over 30 seconds.


## Authorized physical migration result

Follow-up authorization: the user explicitly requests trying 3 Mbps after the
successful 1 Mbps run, with 120 Hz as a desired experimental target. Extend the
same guarded tool to the named 1000000 -> 3000000 transition (register 8: 3 -> 5),
retain all torque-off/configuration checks and the two-rate failure diagnosis,
and test the transition with fake transport before physical execution. No other
register writes or motion are authorized. The 120 Hz target does not supersede
freshness, completeness or existing minimum acceptance requirements.

PASS on 2026-09-11: `baud-apply-1mbps-03` completed seven addressed writes to
register 8, value 3. Every write received an ACK and passed per-device identity,
firmware, ID, rate and torque readback. Full inventory and reopening at 1 Mbps
passed. Torque, mode, PID, return delay, watchdog, limits and motion profiles
remained unchanged; no torque or goal commands were sent. The traffic journal
records 49 READ instructions and 7 WRITE instructions, plus final read-only
verification through the reopened reader. ID3's motion block is unchanged.

Earlier attempts `baud-apply-1mbps` and `baud-apply-1mbps-02` failed their old
preflight comparison before any writes; both classified all seven IDs at 57600.
The tested inactive-goal comparison correction is described above. Its focused
maintenance/read-only suite passes 19 tests; Pylint has no findings.

Local connection facts are saved in ignored `config/local/gello-connection.json`.
This is a connection record, not a station readiness declaration. At this point in the experiment,
explicit diagnostics used `--baudrate 1000000`; generic factory defaults
are not silently changed. Retain the original/refreshed plans and all journals.

| Five-second 1 Mbps diagnostic | Fresh seven-device groups/s | Acquisition p99 | Maximum source gap |
| --- | --- | --- | --- |
| Standard positions | 62.50 | 16.11 ms | 19.15 ms |
| Fast positions | 62.30 | 19.54 ms | 33.87 ms |
| Standard position + velocity | 62.50 | 16.05 ms | 16.36 ms |
| Standard full 83-byte state | 37.04 | 27.05 ms | 27.12 ms |

All short runs completed with no motor status errors and unchanged torque-off
state. Position/velocity is the current compact feedback candidate. The 100 Hz
target is not met; the full layout also misses the 50 Hz minimum. Near-16 ms
quantization remains consistent with host/USB buffering, not a conclusive driver
or dock diagnosis. No latency ioctl, dock change or further EEPROM setting was
introduced. Native CPU time / elapsed time was 0.96-0.99 core equivalents across
these probes (including before/after inventory); process peak RSS was ~24.2 MiB.
Busy receive polling warrants a separately measured optimization. These numbers
are not combined camera/URSim workload acceptance.

The subsequent 60-second normal position/velocity check PASSed its isolated
read-rate and sample-gap slice: 3,751 complete groups, 62.5035 Hz, acquisition p99
16.0454 ms, source-gap p99 16.0730 ms and maximum gap 20.6215 ms. No status or
communication errors occurred; all motors remained at Baud Rate=3, torque off
and without hardware faults. Evidence: `artifacts/gello/1mbps-motion-60s`.
This does not close source-to-control age, loaded timing or the 100 Hz target.
No additional motion/configuration operation is authorized by that result.


## Authorized 3 Mbps follow-up

PASS: after the user's explicit 3 Mbps request, the same implementation was
extended to the named transition 1000000 -> 3000000 (Baud Rate register 3 -> 5).
It retains the earlier 57600 -> 1000000 transition, rejects other transitions,
and classifies failures at only the prepared source/target pair. No rollback,
other register or motion command was added. The focused suite passes 22 tests,
including complete and interrupted 3 Mbps migration and invalid-transition refusal.

Read-only preparation and physical application both passed:
`artifacts/gello/baud-plan-3mbps.json`, `artifacts/gello/baud-apply-3mbps`.
All seven addressed writes received ACKs and passed per-device/full/reopen
verification at 3 Mbps. All torque values remain zero; no other register write
was sent. `config/local/gello-connection.json` now records 3000000 baud; the prior
1 Mbps connection record is retained beside it. Subsequent diagnostics must use
`--baudrate 3000000`. Do not rerun earlier prepared migration plans on this bus.


| Five-second 3 Mbps diagnostic | Fresh seven-device groups/s | Acquisition p99 | Maximum source gap |
| --- | --- | --- | --- |
| Standard positions | 62.50 | 16.05 ms | 18.74 ms |
| Fast positions | 62.50 | 16.05 ms | 18.44 ms |
| Standard position + velocity | 62.50 | 16.05 ms | 16.42 ms |
| Standard full 83-byte state | 43.41 | 23.94 ms | 24.01 ms |

All short runs completed without communication/status faults and with torque off.
The compact-layout rate is unchanged from 1 Mbps; increasing baud alone has not
met the user's 120 Hz experimental target. Larger payloads benefit modestly.
Do not infer that the adapter or dock must be replaced; remaining fixed waiting
requires a separate Mac receive-path investigation. The mainline 50 Hz minimum,
100 Hz acquisition target and freshness limits remain unchanged by this trial.

The 60-second 3 Mbps position/velocity run passed the isolated minimum slice:
3,751 groups, 62.5035 Hz, acquisition p99 16.0544 ms, source-gap p99 16.0933 ms,
maximum gap 21.5696 ms, zero communication/status errors. All seven motors still
reported Baud Rate=5 and Torque Enable=0 afterward. Evidence:
`artifacts/gello/3mbps-motion-60s`. The active bus remains at 3 Mbps.

A ten-group instrumented read-only trace (`3mbps-receive-bursts.json`) showed
11.5-20.3 ms before the first nonempty application read; nine groups then received
their remaining bytes within 0.1 ms, with one 2.5 ms span. Instrumentation itself
perturbs scheduling, so use the uninstrumented 60-second run for gates. This
locates most observed delay before application bytes arrive, without proving a
specific FTDI driver, USB adapter/dock or OS mechanism. No latency setting was
changed. Further latency/CPU optimization remains separate work.

## Final software delivery check

The final three-rate maintenance implementation passed 338 native tests
(5 environment/opt-in skips), 341 amd64 Ubuntu/ROS Jazzy container tests
(2 opt-in container-mount skips), Black, Pylint 10.00/10 without findings, and
`git diff --check`. The installed image matches all 65 current package Python
files by SHA256. Earlier mount checks passed before this maintenance-only change.
The intermediate 1 Mbps image launch encountered a Docker snapshot preparation
error; the preserved failure log and successful retry remain in local evidence.

The existing `ur12e-collection:gello-development` tag was updated, not replaced
with another named development image. Final identity:
`sha256:c96e9fd201cd44c7fe2ece213eeb17ca2c0f8fcb0719d5f114ed3366aded1cee`.
The accepted `ur12e-collection:current` image remains unchanged. This is a tested
working-tree development image, not a committed release or lab deployment.
Logs: `artifacts/gello/3mbps-{native-tests,container-tests,full-lint,image-build}.log`.
