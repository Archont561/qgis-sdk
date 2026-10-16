# Agent instructions

## Session and merge workflow

- For normal repository work, read and follow [the session skill](.agents/skills/session/SKILL.md) at session start or resumption, when selecting backlog work, and when preparing a merge or post-merge handoff.
- For explicit, scoped requests, proceed directly; do not add a proposal-and-wait step unless a material ambiguity needs clarification.
- Before merge or push, verify the final diff and relevant checks. Do not merge, push, or rewrite shared history without the user's explicit authorization.
- PRs must not be squash-merged. Prefer a merge commit (`gh pr merge <number> --merge`).
- After a PR or authorized direct push lands, use the session skill's post-merge closeout: verify the landed commit and CI where accessible, update backlog only for proven work, and report remaining items plus a next-session prompt. Never claim unavailable checks passed.

## Development guidance

- For behavior changes and bug fixes, follow [TDD](.agents/skills/tdd/SKILL.md). For behavior-preserving structural changes, follow [refactor](.agents/skills/refactor/SKILL.md); consult [clean-code principles](.agents/skills/clean-code-principles/SKILL.md) for design decisions.
- Use [the Backlog.md skill](.agents/skills/backlog/SKILL.md) for backlog operations; prefer the CLI over editing task metadata directly.
- For Python QGIS SDK and TypeScript bridge work, consult the [workspace skill](.agents/skills/qgis-sdk/SKILL.md).
- When creating or revising agent skills, follow [Skill Creator](.agents/skills/skill-creator/SKILL.md) and add realistic evaluation prompts.
- Root commands run through Pixi: `pixi run -e bun bun run test` for local tests, `pixi run -e bun bun run coverage` for CI/pre-push coverage gates, and `pixi run -e bun bun run build` for builds. Do not conflate the local test task with the separate 90% coverage checks.
- Keep Pixi dependency pins exact, Bun in its separate environment, source tests outside production source directories, and Codecov LCOV paths repository-root-relative. Do not install `qgis-sdk` as a Pixi path/editable PyPI extra: pixi-pack only carries wheels, so keep Hypothesis and pytest-cov as PyPI wheels in the Python feature and `packages/qgis-sdk/src` on `PYTHONPATH`.
