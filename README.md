# UR12e Collection

A local single-arm collection tool for UR12e, Robotiq Hand-E, a custom GELLO leader, and three RealSense RGB-D views.

The application provides persistent three-camera acquisition, verified MCAP recording, explicit URSim control/session testing, read-only ROS observation and offline calibration. The collection artifact is MCAP plus JSON; LeRobot conversion belongs to a separate repository. Physical control remains disabled; real GELLO and Hand-E actuation are pending. See the module matrix for software, simulation and physical acceptance boundaries.

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

Real physical leader / local URSim rehearsal: see [the live console guide](docs/m13-acceptance/live-leader-ursim.md). This is a lightweight motion preview with read-only motor acquisition, HOME/start/stop controls and no camera or recording workload. Production teleoperation and recording acceptance remain separate.
