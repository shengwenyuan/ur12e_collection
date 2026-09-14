# UR12e Collection

A local single-arm collection tool for UR12e, Robotiq Hand-E, a custom GELLO leader, and three RealSense RGB-D views.

The application provides persistent three-camera acquisition, verified MCAP recording, physical GELLO teleoperation, simulator testing, read-only ROS observation and offline calibration. The collection artifact is MCAP plus JSON; LeRobot conversion belongs to a separate repository. Physical UR and Hand-E control require an operator-started session. Leader motor writes remain disabled. See the module plans for software, simulation and physical acceptance boundaries.

## Daily collection on the provisioned PC

```sh
ur12e gello
ur12e gello --output ~/another-dataset
```

The default output is `~/ur12e-data`. Launch from any working directory; the
installed deployment supplies the existing station configuration and `current`
image. Space requests HOME, starts recording, then stops/saves the episode;
`a` discards and `q` finishes the session. Ctrl+C uses the existing stop/exit path.
Starting this command is the operator's explicit session launch, including SDK
initialization; motion remains subject to the existing keyboard/state gates.
`dagger` is reserved for future implementation and is currently rejected.
See the [entrypoint and installation guide](docs/m09-session/collection-entrypoint.md).

- [Requirements and stable module IDs](meta_plan.md)
- [Current module acceptance matrix](docs/m13-acceptance/simulator-matrix.md)
- [Current image and cleanup inventory](docs/m01-runtime-deployment/image-consolidation.md)
- [Development and deployment quickstart](docs/m01-runtime-deployment/quickstart.md)
- [M01 implementation and acceptance](docs/m01-runtime-deployment/plan.md)
- [M08 matching plan](docs/m08-frame-matching/plan.md)
- [M11 storage plan](docs/m11-storage/plan.md)
- [Camera-only batch plan](docs/m13-acceptance/plan.md)
- [Lab deployment and acceptance](docs/m13-acceptance/lab-runbook.md)
- [Offline validation and next lab deployment](docs/m11-storage/offline-validation.md)
- [Google-derived engineering conventions](skills/project-engineering.md)

## Local development

Use Python 3.12. On this Mac, `uv` can provision the existing development environment without lab connectivity once its dependencies are cached:

```sh
uv venv --python 3.12
uv pip install --require-hashes -r requirements/development.txt
uv pip install --no-deps -e .
source .venv/bin/activate
./scripts/check
ur-collect --help
```

Use one daily Docker image, `ur12e-collection:current`, for collection, development tests and simulator clients. Build with `docker build --platform linux/amd64 --target development -t ur12e-collection:current .`, then run `./scripts/run dev doctor --format json --require-mounts`. The development container has no network or hardware access. Ubuntu deployment and explicit physical probes are described in the quickstart.

Formal plans and actual acceptance results live under `docs/`. Temporary ideas, station identities, recordings, and release artifacts stay in ignored local directories. Do not infer hardware readiness from passing software tests.

Native PC leader → Isaac kinematic follower: see the
[M14 launch and acceptance guide](docs/m14-digital-twin/native-teleop.md).
The Ubuntu PC owns USB acquisition, shared teleoperation and local simulated
execution. Configure external scene paths in `config/teleop.isaac.json`.
No Mac input process or URSim intermediary is used. This first entry controls
motion only; camera/MCAP acceptance stays with the collection session.

For an independent read-only 3D view of actual URSim joint angles, run
`.venv/bin/python scripts/sim_viewer.py` and open http://127.0.0.1:8787.
It reuses the installed image without changing the control console. See the
[viewer guide](docs/m13-acceptance/readonly-viewer.md).

Camera-specific AprilGrid calibration now has `ur12e cali --left|--right|--wrist`
replay/solve entries. See the [waypoint JSON and usage contract](docs/m12-calibration/replay-usage.md)
and [software versus physical acceptance](docs/m12-calibration/keyboard-aprilgrid.md).
This increment is not yet deployed or physically calibrated.
