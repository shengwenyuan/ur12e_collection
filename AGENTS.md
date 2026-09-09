# Project Instructions

- Write all project documentation and plans in English. Conversation replies may follow the user's language.
- Use the repository skill [plan-module-work](.agents/skills/plan-module-work/SKILL.md) for durable mainline feature/module planning, implementation, and acceptance work.
- Keep the stable module and acceptance IDs defined in [meta_plan.md](meta_plan.md).
- Before implementing a durable feature/module, write its formal plan under `docs/` and align the concrete scope and acceptance criteria with the user. Existing explicit alignment remains valid for that scope; do not ask again without a material change.
- After implementation, update the same formal plan with actual test and acceptance conclusions, including anything unrun or unresolved.
- Keep temporary requirement ideas in the Git-ignored root `plans/` directory. Promote accepted work into `docs/` before implementation; versioned documents must remain understandable without `plans/`.
- Every plan, including temporary plans and the meta plan, must prominently state: **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**
- Apply the Google-derived [local engineering profile](skills/project-engineering.md) to code, build, test, and delivery work. It adapts the copied `skills/google-cicd-*` workflows for this local collector; cloud infrastructure is not a default dependency.
