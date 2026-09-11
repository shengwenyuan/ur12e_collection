# Disposable lab-image replay

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

These test tools never open camera, robot or motor-control connections. Inputs,
raw caches and run outputs belong under ignored `artifacts/`; deleting those
folders removes downloaded data and generated recordings without touching the
collector. The formal scope and acceptance record live in
[the M04 integration plan](../../docs/m04-gello-adapter/hardware-integration.md).

```bash
python tests/replay/cache.py /path/to/complete/episode --output artifacts/cache
python tests/replay/run.py artifacts/cache --output artifacts/replay-run \
  --seconds 40 --revision YOUR_REVIEWED_REVISION
```

Run in the project's provisioned environment with the recording dependencies.
The runner waits for writer initialization, prefetches at most one raw image pair
per producer and gives each of three producers eight queue slots. Matching uses
the station's 16.7 ms skew and 75 ms wait; the mainline writer retains four group
slots and its existing codecs. Overflow or corruption fails the run. The output
includes the original manifest, actual delivery schedule and independently
verified MCAP episode. A complete file does not imply all performance gates pass.

`simulated=true`, replay camera IDs, the cache hash in the snapshot task and
original acquisition times explicitly identify replay. Historical UR/Hand-E
observations are not replayed as current feedback. The camera archive does not
include the separately recorded physical leader trace: mixed-source archival and
the native-to-container clock bridge remain separate integration work.

Only accepted source image pairs exist. Lost/rejected exposures, USB traffic and
RealSense alignment costs cannot be recovered. Re-encoded RGB is a second H.264
generation; depth is checked pixel-for-pixel against the original cache hashes.
Looped inputs retain original timestamps in provenance while replay timestamps
and sequence numbers advance. Memory maps use bounded owned frame copies, but
reported RSS can include resident file-backed pages; do not treat it as anonymous
heap usage or compare native Mac and emulated amd64 performance directly.


## Shared control replay

`rig.py` injects three persistent recorded-image producers into the standard
recorder. The verified local URSim launcher accepts `--leader-trace`,
`--leader-speed`, `--camera-cache` (host path) or the explicit temporary
`--camera-volume ur12e-replay-cache-20260911`. The 5 GiB replay profile prefaults
the cache before control and uses three encoder jobs. It preserves all source
identities, original capture metadata and explicit non-contemporaneous provenance.
The old camera-only runner above remains a distinct four-slot serial profile;
do not compare its result as though it used the shared-control resource layout.

```bash
python scripts/sim_control.py session --client-image YOUR_CANDIDATE \
  --installed-package --client-memory 5g --episodes 20 --seconds 40 \
  --leader-trace /path/to/samples.jsonl --leader-speed 3.5 \
  --camera-volume ur12e-replay-cache-20260911
PYTHONPATH=tests python -m simulation.acceptance artifacts/simulator-control/BATCH
PYTHONPATH=tests python -m replay.report artifacts/simulator-control/BATCH
```

The first command can control only the verified isolated local URSim service.
It cannot use a physical host argument. The two audit/report commands only read
files: acceptance reopens and decodes MCAP; timing-cost reports summarize source
age, view skew, command gaps, queue/encode metrics and bytes without changing
acceptance. Full-load failure on Mac remains failure until a fresh unchanged
gate passes; Ubuntu with live devices needs separate acceptance.


`--camera-pacing uniform30` adds a separate real-pixel workload comparison with
30 Hz replay timestamps and fixed 0/4/8 ms view phases. The default `original`
keeps historical receipt/exposure timing, including source gaps. Both retain
original acquisition provenance. Never present uniform pacing as hardware
synchronization or as a pass of the original-timing replay. Optional
`--client-cpus 4-9` records an explicit Docker CPU set in the launch manifest.

After capture, compare second-generation RGB against the immutable cache:

```bash
PYTHONPATH=tests python -m replay.quality /path/to/completed/episode /path/to/cache
```

The tool decodes every RGB packet, checks role/identity association, and reports
PSNR without inventing a pass threshold. Depth equality remains the independent
MCAP verifier's gate.
