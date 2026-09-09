---
name: plan-module-work
description: Plan and track durable mainline features and modules in this collection repository. Use before implementation or substantial behavior changes and when updating test or acceptance results. Maintain English plans under docs/, align them with the user, and keep temporary ideas in ignored plans/. Routine documentation edits do not need a new implementation plan.
---

# Plan Module Work

Maintain a reviewable plan-to-implementation-to-acceptance record for this repository. Resolve repository paths from the working tree, not from the installed skill directory.

## Required conventions

- Write all documentation, plans, templates, and acceptance reports in English. Conversation may follow the user's language.
- Read `AGENTS.md`, `meta_plan.md`, and the relevant existing `docs/` plans before changing a durable feature or module.
- Use stable module IDs and directory names from `meta_plan.md`. IDs identify responsibilities, not execution order. Never renumber or reuse an ID; append new IDs and keep references for retired modules.
- Include this exact prominent line near the top of every plan, including `meta_plan.md` and temporary plans:

  > **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Interpret economical code as removing unnecessary logic and duplication, not code golf. Prefer clear names, direct control flow, and abstractions that serve real boundaries. Do not add speculative frameworks or compress code at the expense of readability.

## Classify and locate the work

- **Durable mainline work:** create or update a version-controlled plan under the module's assigned `docs/mXX-module-name/` directory before implementation. Use `plan.md` for the module or a descriptive feature filename for later durable additions. A behavior-changing fix should update its existing plan rather than create a parallel account.
- **Temporary ideas:** use root `plans/` for exploratory requirements, options, and disposable notes. Ensure root `.gitignore` contains `/plans/`. Never force-add this directory, create tracked exceptions, or make an accepted requirement depend solely on it.
- **Routine documentation corrections or minor maintenance:** update the relevant document/plan directly; do not invent a new implementation approval cycle.

Create directories when actual content needs them. Do not scaffold empty plans for all modules. If work crosses modules, assign one primary plan and reference the affected contracts instead of duplicating decisions.

If temporary files are already tracked, report them and handle removal from the index without deleting the local notes or changing unrelated tracked files. Do not claim an ignore rule alone untracks existing content.

## Before implementation

1. Identify the module, current decisions, relevant interfaces, and unresolved requirements. Use read-only inspection and existing evidence to make the proposed work concrete.
2. Write a concise draft under `docs/`. Use [references/plan-template.md](references/plan-template.md) for the necessary fields, adapting its length to the work. Include scope/non-goals, dependencies, interfaces and units, ordered implementation steps, and specific acceptance cases. State hardware-motion requirements separately from software or camera-only checks.
3. Present the written plan to the user with its path, module ID, meaningful choices, and acceptance scope. Obtain alignment before implementing the durable feature/module. A feature request or agreement with high-level meta requirements does not approve an unwritten implementation plan.
4. Record the agreed scope, date, and relevant conversation decision in that plan. Do not invent approval or mark a draft aligned merely because it was written. If earlier explicit alignment already covers this concrete plan and scope, record it and continue without requesting the same approval again.

Until required alignment exists, continue useful inspection or planning, but do not implement the dependent feature. If this rule causes a pause, cite this SKILL.md and explain that the user's project workflow requires alignment of the concrete plan before implementation.

## During implementation

Implement the aligned scope and keep the plan current when findings change interfaces, behavior, or acceptance. Re-align material scope changes before implementing those changes. Routine implementation choices within the agreed design do not need another permission request.

Do not silently replace a confirmed requirement with a proposal. Keep unresolved alternatives explicit. Preserve device/control ownership boundaries and existing authorization for real hardware; agreement on a software plan is not evidence that a hardware test has passed.

## After implementation and testing

Update the same formal plan before reporting completion:

- Describe the resulting behavior and implementation changes relevant to the plan.
- Record actual checks, commands or reproducible procedure, environment, software/image revision when available, and outcomes under the stable acceptance IDs.
- Mark each applicable case `PASS`, `FAIL`, `NOT RUN`, or `BLOCKED`; explain failures, unrun checks, and blockers briefly. Do not invent revisions or report planned tests as executed.
- Separate software validation, camera-only shadow results, and real-robot acceptance. Fake-device tests or a Mac container run do not establish Ubuntu hardware acceptance.
- State what remains and the next acceptance action. Keep a module in `implemented / acceptance pending` if required hardware evidence is missing; use `accepted` only after its agreed acceptance has actually passed.

Keep durable conclusions in `docs/`, even when large logs remain local. Link useful artifacts and summarize enough that a fresh checkout remains understandable without ignored `plans/` content. Update the meta plan only when module scope, decisions, or summarized status changes; do not duplicate detailed test logs there.

Useful plan states are `draft`, `aligned`, `implementing`, `implemented / acceptance pending`, and `accepted`. Track failed/blocked cases explicitly without presenting incomplete work as accepted.

## Final consistency check

Verify English text, the code-style requirement, stable IDs, working references, and the distinction between agreed and proposed behavior. Confirm `/plans/` is ignored and not tracked. For acceptance updates, check that every claimed result has an actual recorded run and that remaining work is visible.
