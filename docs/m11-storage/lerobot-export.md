# M11: Explicit Offline LeRobot v3 Projection

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned within the autonomous simulator sprint / implementing, 2026-09-10.

Implement an offline export from independently verified, retained controlled MCAP
episodes. Use official Hugging Face LeRobot 0.6.1 at commit
`7e241bd630a3719a56157a497ce5d08f244784f1`, with its actual writer and loader.
Install export dependencies in a separate environment: Torch/dataset dependencies
must not enter the collection runtime merely to support offline conversion.
No downloads, hub push or model invocation occur during export.

The first explicit projection is **RGB plus six arm joints**. Require an
`--rgb-arm-only` flag and an explicit action source (`sent_command` or
`leader_intent`). Preserve missing Hand-E values; never fill a seventh joint with
zero or normalized guesses. Reject read-only episodes, partial files, discarded
outcomes, mixed source contexts and missing/stale state/action associations.
Original MCAP RGB-D and complete control streams remain the authoritative data.
This projection does not claim lossless depth export: the pinned package's default
depth-video path quantizes depth, which is unsuitable for replacing raw uint16 PNG.

Use accepted wrist groups as observations. Select the latest actual follower
sample and selected action at or before the wrist host receipt, with a maximum
50 ms age. Do not interpolate, reuse camera groups, synthesize frames or infer
commands from actual state. Reject missing associations and non-contiguous camera
sequences rather than silently compressing a missing-frame interval.

LeRobot creates nominal `frame_index / 30` timestamps. Preserve each camera's
original acquisition timestamp and each selected control receipt as separate
int64 features; declare the nominal playback clock and exact source clocks in
`export.json`. This is an explicit training projection, not a rewritten raw clock.
Keep camera source IDs, selected sequence indices, source episode checksums and
full immutable snapshots in the export manifest. RGB uses explicit H.264 settings;
measure second-encode cost/quality and retain the original compressed stream.

Write to a reserved sibling `.partial` directory, finalize through LeRobot,
reopen using its real local loader with Hub access disabled, verify frame counts,
features and numerical state/action values, then rename atomically. Failed exports
remain partial and never replace an existing dataset. Accepted output contains
v3 Parquet, MP4 and metadata plus the provenance manifest. Do not modify input files.

Tests: deterministic association and omitted-field rejection, multi-episode
boundaries, stale/discarded/partial/mixed-source failures; actual pinned loader on
short URSim-generated episodes; report bytes and conversion time separately from
capture performance. Wider physical training semantics and gripper-enabled export
remain pending. This implementation choice uses the user's delegated authority to
bypass unresolved hardware details without pretending they are resolved.

References: [official v3 dataset documentation](https://huggingface.co/docs/lerobot/lerobot-dataset-v3),
[pinned writer/loader](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/datasets/lerobot_dataset.py).


## Results and use (2026-09-10)

M11 offline export slice PASS with the real pinned official writer and loader.
`artifacts/lerobot-validation/sim-rgb-arm-1789026605814995000` contains 90 frames;
`multi-1789027689360881000` contains 1,291 frames across two retained episodes.
All projected numeric values match exactly, including int64 clocks. Sampled RGB
mean absolute error is at most 0.719/255 after the second H.264 encode. The latter
also reopens after atomic publication and decodes across episode boundaries.
Hub access is disabled throughout. A source with non-contiguous wrist frames was
rejected rather than silently resampled. Failed writer output remains partial;
existing partial directories are never modified by a conflicting export.

The first 90-frame conversion took 0.894 s after dependency import and initial
source verification, producing 171,245 bytes excluding `export.json`. This RGB/arm
projection excludes depth and is not an equivalent replacement-size comparison
with MCAP. Export quality on physical imagery remains NOT RUN.

`requirements/export-macos.txt` records the tested optional Python 3.12 Mac
environment, including exact official LeRobot source. It is independent of the
runtime lock and is not a Linux export acceptance claim. To reproduce locally:

```sh
uv venv --python 3.12 artifacts/export-env
uv pip install --python artifacts/export-env/bin/python -r requirements/export-macos.txt
PYTHONPATH=src artifacts/export-env/bin/python -m ur12e_collection episode export \
  /absolute/retained-episode --output /absolute/new-dataset \
  --action-source sent_command --rgb-arm-only
```

Use `leader_intent` explicitly when that is the desired training action. The
original six raw arm joint values remain radians; real gripper-enabled projection
and real training-policy evaluation remain deferred. Acquisition never imports
this optional ML environment.
