# UR12e Collection Engineering Profile

This is the local adaptation of the Google CI/CD skills copied by the user from the Piper repository. Preserve their reusable engineering guidance; the inherited cloud workflows and examples are reference material, not the deployment target of this project. This profile takes precedence over conflicting defaults in those copied skills and their references.

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

## Scope and workflow

- The product is a local Ubuntu 24.04 / ROS 2 Jazzy collector with Docker delivery. Development may run on Mac without lab connectivity. No GCP project, cloud account, registry, Terraform, Kubernetes, cloud telemetry, or automatic push/deploy is required.
- Read `AGENTS.md` and use the repository `plan-module-work` skill for durable module work. Keep module plans and acceptance in `docs/`, and disposable ideas in ignored `plans/`. Reuse explicit alignment; the copied YAML-only planning format and repeated implementation-choice prompts do not apply locally.
- Use available local tools and CLIs. On failure, stop dependent steps, report the cause, and make routine reversible fixes within the user's authorization. Continue independent work. Ask only for missing decisions or authorization actually required by the next action; do not halt all work because an unrelated probe failed.
- Enable inherited cloud workflows only for a future explicit cloud request. They do not authorize uploads or infrastructure changes in the current project.

## Code and review

Follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html): four-space indentation, an 80-character code line target with the guide's exceptions, clear module imports, explicit resource ownership, and useful Google-style docstrings. Use type annotations at public interfaces. Keep functions direct, avoid mutable global state and unnecessary indirection, and explain non-obvious units, timing, and failure behavior. Economical code means less duplication and accidental complexity, not compressed spelling or code golf.

Run lint, formatting, and meaningful behavior tests for implemented code. Pylint is the Google baseline; pin concrete tooling and project configuration with the first code-bearing module. Explain narrow suppressions; do not disable checks broadly to make a build green. Documentation-only bootstrap does not need placeholder test suites or an empty CI workflow.

## Build and delivery

- Prefer the official Jazzy base image, then record immutable digests and resolved dependency versions. Project version constraints override inherited advice to use the latest runtime or automatic base-image updates.
- Reuse dependency definitions, copy dependencies before frequently changing source, use multi-stage builds where useful, and keep build tools out of the release runtime. Sort package lists and avoid unnecessary layers and packages.
- Run production containers as non-root, with explicit host-mount ownership and only required device access. Do not copy a generic numeric UID without checking the station's file permissions. Do not use privileged mode as a default fix.
- Exclude Git internals, temporary plans, recordings, station identities, credentials, and local environments from the build context. Before commits/builds/delivery, review the selected files for secrets. Use an available local scanner or an explicit staged/context review; the inherited named `scan_code_for_secrets` tool is not assumed available. Never label a manual review as an automated scan.
- Keep failed checks visible; do not deploy a failed artifact. Record image identity, platform, dependency versions, checksums, and validation conclusions. Deliver a tested local image archive and preserve mounted configuration/data across replacement. Registry publishing and automated deployment require separately defined scope.
- Separate Mac software checks, Ubuntu container checks, camera shadow checks, and motion acceptance. A successful image build establishes none of the latter by itself.
