# Agent instructions

> This file is two documents in one. The regions between `agents-md` markers are
> generated from the repository by `bun run agents` (`@eugeniughelbur/agents-md`
> plus the corrections this tree needs) and are checked by CI; everything outside
> them is written by hand and is never touched by a refresh.

<!-- agents-md:begin id=overview -->
## Overview

A Python-first foundation for QGIS plugins: plain classes in, a loadable plugin out - with a typed TypeScript SDK and web components for interfaces hosted in QWebEngineView.

Stack: Python 3.11-3.14 for the SDK (Pixi pins the environments), TypeScript for the bridge and the web components, Bun for the JavaScript workspace.
<!-- agents-md:end id=overview -->

<!-- agents-md:begin id=structure -->
## Project structure

Top-level: `apps/`, `automation/`, `backlog/`, `docs/`, `examples/`, `packages/`, `scripts/`, `tests/`.

The SDK's suite is `packages/qgis-sdk-python/tests`; `apps/docs` is the documentation site; `backlog/` holds the task and decision records.
<!-- agents-md:end id=structure -->

<!-- agents-md:begin id=git -->
## Git & PR workflow

Default branch `main`. Remote: <https://github.com/Archont561/qgis-sdk>
<!-- agents-md:end id=git -->

## Session and merge workflow

- For normal repository work, read and follow [the session skill](.agents/skills/session/SKILL.md) at session start or resumption, when selecting backlog work, and when preparing a merge or post-merge handoff.
- For explicit, scoped requests, proceed directly; do not add a proposal-and-wait step unless a material ambiguity needs clarification.
- Before merge or push, verify the final diff and relevant checks. Do not merge, push, or rewrite shared history without the user's explicit authorization.
- PRs must not be squash-merged. Prefer a merge commit, merged **locally** with a conventional-commit message so lefthook's Convco gate passes - `git merge --no-ff -m "chore(scope): <description>"`. Do not use `gh pr merge --merge`: GitHub's auto-generated "Merge pull request #N from ..." message is not conventional and fails Convco. Rebase-and-merge (`--rebase`) is allowed only if the user explicitly asks for it.
- Open and watch pull requests through `automation.pr`, never a hand-written `gh` sequence: `pixi run automation pr_open` (or `python -m automation.pr open [--title ...] [--body-file ...] [--base ...] [--draft]`) pushes the branch, refuses a branch whose pull request is already open, and takes the commit list as the default body; `pixi run automation pr_watch` (or `python -m automation.pr --pr <n>`) polls the checks and breaks on the first failure. If a body has to be repaired afterwards, patch it with `gh api -X PATCH --input <file>`: `gh pr edit` fails here on the retired GraphQL `projectCards`, and `gh api -f` sends strings rather than JSON types.
- After a PR or authorized direct push lands, use the session skill's post-merge closeout: verify the landed commit and CI where accessible, update backlog only for proven work, and report remaining items plus a next-session prompt. Never claim unavailable checks passed.

## Development guidance

- **New features start with the TDD and BDD skills, before any source edit.** Read [TDD](.agents/skills/tdd/SKILL.md) and [BDD scenarios](.agents/skills/bdd-scenarios/SKILL.md) (with [BDD patterns](.agents/skills/bdd-patterns/SKILL.md)) as the first step of the work, then write the acceptance scenario for the behaviour and a failing test at the agreed seam before writing the implementation. The order is: scenario → red test → minimal green code → refactor, one vertical slice at a time; no feature code lands whose behaviour is neither specified in `packages/qgis-sdk-python/tests/features` nor proven by a test that failed first. Retro-fitting tests for code that was written first is a defect to fix in the same change, not a substitute.
- For behavior changes and bug fixes, follow [TDD](.agents/skills/tdd/SKILL.md). For behavior-preserving structural changes, follow [refactor](.agents/skills/refactor/SKILL.md); consult [clean-code principles](.agents/skills/clean-code-principles/SKILL.md) for design decisions.
- Use [the Backlog.md skill](.agents/skills/backlog/SKILL.md) for backlog operations; prefer the CLI over editing task metadata directly.
- For Python QGIS SDK and TypeScript bridge work, consult the [workspace skill](.agents/skills/qgis-sdk/SKILL.md).
- For behaviour specifications and the Gherkin scenarios under `packages/qgis-sdk-python/tests/features`, follow [BDD scenarios](.agents/skills/bdd-scenarios/SKILL.md) for writing them and [BDD patterns](.agents/skills/bdd-patterns/SKILL.md) for Given/When/Then structure, feature files and acceptance criteria. The scenarios are linted with `pixi run automation lint_features` - gherlint behind `automation/ci check-gherkin`, policy in [gherlint.toml](gherlint.toml); a new `*.feature` directory has to be added to `FEATURE_DIRECTORIES` in `automation/ci/_checks.py` or the check fails.
- For a read-only code-quality audit of source, a diff or a package - evidence, severity, and one backlog task per validated follow-up - follow the [audit skill](.agents/skills/audit/SKILL.md).
- When working from an Arena sandbox where Pixi, Bun or the network are unavailable, follow the [arena skill](.agents/skills/arena/SKILL.md) for the fallback checks, branch discipline and GitHub mechanics.
- Use `pathlib.Path` for every filesystem path, in source, tests and scripts alike: build paths with `Path(...) / "child"`, inspect them with `.exists()`, `.is_file()`, `.is_dir()`, `.stat()`, read and write them with `.read_text()`, `.write_text()`, `.open()`, and move them with `.replace()`, `.rename()`, `.unlink()`, `.mkdir()`. `os.path` is out of bounds - `os.path.join`, `split`, `dirname`, `basename`, `exists`, `isfile`, `isdir`, `abspath`, `relpath`, `expanduser`, `normpath` and `getsize` all have a `Path` spelling - and so are the bare `open()` builtin and the `os.replace`/`os.link`/`os.remove`/`os.makedirs` functions. Directory traversal goes through `qgis_sdk_tools.paths.walk_files`, which prunes the same way `os.walk` does on the 3.11 this package still supports. Ruff enforces this with its `PTH` rules (`extend-select` in `ruff.toml`), so the gate fails a path written the old way; a genuine exception needs a comment saying which interop needs it.
- Prefix every SDK-defined exception class (Python or TypeScript) with `QgisSdk` (for example, `QgisSdkError` and `QgisSdkScopeClosedError`), including internal subclasses. Export only prefixed exception names; do not keep unprefixed aliases. Structured error `code` values are independent of class names.
- When creating or revising agent skills, follow [Skill Creator](.agents/skills/skill-creator/SKILL.md) and add realistic evaluation prompts.
- Keep new Python code inside the clean-code limits (Rude + `rude-clean-code`: a function of at most 30 lines, 5 parameters, 5 returns and 10 locals; a class of at most 200 lines and 15 methods; nesting of 4, a boolean chain of 3, 10 branches) - thresholds live in `[tool.rude]` in the root `pyproject.toml`. There is no budget and no baseline: the rules are `WARNING`s and `rude check` exits 0 regardless, so the gate is `pixi run automation clean_code` (or `python -m automation.clean_code [paths]`), which fails on any finding in the tree it is given. It is enforced three times - lefthook on the staged files at commit, lefthook on the whole tree before a push, and the `Fast gates` CI job - and a finding is fixed by extracting the definition, never absorbed (decision-82). Raising a threshold belongs in a new `backlog/decisions/` record, not in a config edit.
- A test that simulates a missing dependency must neutralise the *binding its caller reads*, not a name that happens to resolve to it: patching `pkg.name` when `pkg/__init__.py` re-exports it with `from ._impl import name` binds nothing, and dropping a package's own `sys.modules` entry leaves its submodules cached. Patch the defining module (and assert the pin took effect) or purge the whole subtree. The suite runs both layers in one process on every pull request precisely because these only fail once the thing they simulate is already true (decision-84).
- Repository automation has one entry point: `pixi run automation <task>`, with the tasks declared in `dodo.py` and implemented in `automation/`. `pixi run automation list` is the list; do not add a one-line Pixi task for Python work - add a task there. `automation/` must not import `doit`.
- The root `scripts/` directory holds `scripts/restore.sh` and nothing else - it is the sandbox entry point. Anything else that runs here, Python or JavaScript, lives in `automation/`, where it is importable and covered by tests: `automation/readme/` renders the landing page (`bun run readme`), `automation/agents/` refreshes AGENTS.md (`bun run agents`). alint's `scripts-are-restore-only` and `scripts-nest-restore-only` rules fail a stray file, so a new script belongs in `automation/` from the start.
- Root commands run through Pixi: `pixi run -e bun bun run test` for local tests, `pixi run -e bun bun run coverage` for CI/pre-push coverage gates, and `pixi run -e bun bun run build` for builds. Do not conflate the local test task with the separate 90% coverage checks.
- Keep Pixi dependency pins exact, Bun in its separate environment, source tests outside production source directories, standalone developer scripts in the package `scripts/` directory covered by `tests/scripts/`, and Codecov LCOV paths repository-root-relative. Do not install `qgis-sdk` as a Pixi path/editable PyPI extra: pixi-pack only carries wheels, so keep Hypothesis and pytest-cov as PyPI wheels in the Python feature and `packages/qgis-sdk-runtime/src` plus `packages/qgis-sdk-tools/src` on `PYTHONPATH`.
