# Formal Development Plans

This directory contains version-controlled plans for durable mainline features and modules. The stable registry and current requirements are in [meta_plan.md](../meta_plan.md).

Create `docs/mXX-module-name/plan.md` when preparing a module for implementation, using the exact directory assigned in the registry. A later durable feature can use another descriptive Markdown filename in that module directory. Do not create empty plans for every module merely to populate the tree.

Each plan must identify its module, scope, status, user alignment, interfaces, ordered implementation steps, acceptance cases, and actual validation results. Preserve the `Mxx-Axx` identifiers from the meta plan; add stable case suffixes for detailed scenarios rather than reusing an ID for different behavior.

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Write plans and reports in English. Prepare the concrete plan before asking the user to align on development. Implement within the aligned scope, then update that same plan with tests run, environment/version, pass/fail/not-run conclusions, limitations, and remaining work. Software-only success never implies hardware acceptance.

Use the [plan-module-work skill](../.agents/skills/plan-module-work/SKILL.md) and its [plan template](../.agents/skills/plan-module-work/references/plan-template.md). The foundation implementation and current acceptance results are recorded in [M01: Runtime Architecture and Deployment](m01-runtime-deployment/plan.md). M02/M03/M04/M07/M08/M10/M11 have scoped plans for their implemented foundation or diagnostic slices; full module acceptance remains separate.

The [development environment record](development-environment.md) documents the initial Docker and repository bootstrap, separately from M01 implementation acceptance.

[M12: Independent Visual Calibration](m12-calibration/plan.md) records the aligned two-round requirements and the proposed script/capture interfaces. Offline detection, geometry, immutable evidence and activation are implemented and software-tested; physical capture and accuracy acceptance remain pending.

Temporary ideas belong in the ignored root `plans/` directory. Never rely on that directory as the only record of an accepted requirement or an acceptance result. Create it locally when needed; a fresh checkout does not contain its ignored contents.

The [M13 camera batch](m13-acceptance/plan.md) and
[lab runbook](m13-acceptance/lab-runbook.md) cover persistent camera-only collection.
[M09](m09-session/plan.md) records the shared episode lifecycle and remaining
robot-session boundaries.

The [accepted software baseline](m13-acceptance/software-baseline.md) closes the
passed software scope and lists the remaining physical-camera acceptance checks.

[M05 communication research](m05-hande-adapter/communication-notes.md) records the confirmed UR12e IP and unverified Hand-E transport candidates.

The official [URSim environment](m06-control-motion/ursim-setup.md) and
[quickstart](m06-control-motion/ursim-quickstart.md) cover local basic motion
simulation in Docker Desktop. Gazebo is excluded; physical control acceptance
remains separate.

The current [M01–M13 simulator matrix](m13-acceptance/simulator-matrix.md)
separates accepted simulation/software behavior from remaining hardware work.
The [read-only ROS observer](m10-data-contract/ros-observation.md),
[official LeRobot export](m11-storage/lerobot-export.md) and
[offline calibration commands](m12-calibration/offline-usage.md) have independent
acceptance records and explicit optional/deferred boundaries.
