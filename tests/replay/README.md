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
