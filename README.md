# UR12e Collection

A local single-arm collection tool for UR12e, Robotiq Hand-E, a custom GELLO leader, and three RealSense RGB-D views.

The current foundation provides a ROS 2 Jazzy Docker environment, software diagnostics, versioned station drafts, data contracts, a GELLO unavailable stub, and explicit camera/UR probes. Leading, ZERO/READY motion, calibration, and episode recording are not implemented yet.

- [Requirements and stable module IDs](meta_plan.md)
- [Development and deployment quickstart](docs/m01-runtime-deployment/quickstart.md)
- [M01 implementation and acceptance](docs/m01-runtime-deployment/plan.md)
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

To use Docker, build the development target and run `./scripts/run dev doctor --format json --require-mounts`. The development container has no network or hardware access. Ubuntu deployment and explicit physical probes are described in the quickstart.

Formal plans and actual acceptance results live under `docs/`. Temporary ideas, station identities, recordings, and release artifacts stay in ignored local directories. Do not infer hardware readiness from passing software tests.
