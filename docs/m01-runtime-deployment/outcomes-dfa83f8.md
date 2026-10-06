# M01: Episode Outcome Deployment dfa83f8

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: installed software checks and activation PASS; physical acceptance pending.

On 2026-10-07, the operator requests push and PC deployment of the aligned M09
success/fail/aborted implementation. Native software checks pass: 760 tests,
five skips, Black and Pylint. Target `ur12e-collection` is Flexlab; inspection
found no active collector, only the separate URSim service. No hardware launch
or recording is part of deployment.

Build a revision-tagged candidate from the cached `09fe5aa` image and an offline
wheel. Preserve station-local configuration and all seven task routes. Run
installed-package integrity, station validation and software tests with no
network or devices. Before activation, recheck that no collection started and
that current configuration/image still matches the captured identity. Promote
source and image together only after checks pass.

Retain `09fe5aa` as the immediate `bak`. Preserve the preceding `bak` image and
deployment reference under an identity-specific backup name before replacing
those aliases. Delete no images, source directories or data. Motion parameters
remain following 24 deg/s and 30 deg/s2, HOME 6 deg/s and 12 deg/s2.

## Delivery result

M01-A01/A02 installed checks and activation: PASS.

- Source revision: `dfa83f8c2fa4261062583faffcdef54abbf58ae5`, pushed to remote main.
- Active source: `~/ur12e-current` resolves to `~/ur12e-releases/dfa83f8/source`.
- `ur12e-collection:current` and `:dfa83f8` select linux/amd64 image
  `sha256:7edda7981e14311077c6319c47f307d3efdead5482e04d80d64d1456a340b67c`.
- Reused all prior `09fe5aa` layers. Wheel construction used cached local tools;
  installation used `--no-index --no-deps`. No dependency download was needed.
- All 122 installed package files match the wheel. The installed full suite
  passed 760 tests with five skips (25.17 s), with no devices or network,
  two CPU equivalents and 2 GiB memory. ROS-specific skips remain explicit.
- Active configuration and seven task routes are preserved; HOME-free leader
  binding, station camera metadata and launcher help validate after promotion.
- Immediate backup: `ur12e-collection:bak` selects `80cd4823c9ec` (`09fe5aa`);
  `~/ur12e-bak` resolves to `~/ur12e-releases/09fe5aa/source`.
- Earlier backup: `ur12e-collection:bak-e98510ee47f8` retains image `e98510ee47f8`;
  `~/ur12e-bak-e98510ee47f8` resolves to the untouched `~/ur12e-real-teleop`.
  Existing revision tags remain. Nothing was pruned or deleted.

PC receipt and logs: `~/ur12e-releases/dfa83f8/activation.json`, `before.json`,
`installed-checks.log`, `build.log`, source/context archives and `SHA256SUMS`.
Local copies: `artifacts/deployment-dfa83f8/`. No collection, camera or hardware
control was started. Physical acceptance of the new outcomes: NOT RUN.
The existing entrypoint remains `ur12e gello`.
