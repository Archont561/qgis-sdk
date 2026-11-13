---
id: TASK-168
title: Keep the vendored skill bundles out of the commit hooks and the Clean Code gate
status: Done
assignee: []
created_date: '2026-11-13 11:40'
updated_date: '2026-11-13 11:40'
labels: []
dependencies: []
ordinal: 168000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`.agents/` is 59 tracked files of skill bundles copied from upstream, kept for their instructions rather than as this repository's source. The Clean Code gate was already told that - `SCOPE` names `packages`, `automation`, `scripts`, `tests` and `examples` and nothing else - but the commit hooks were not: `01-ruff-lint`, `02-ruff-format` and `03-clean-code` matched every `*.py` in the checkout, and the whole-tree Ruff run that CI and `pixi run automation lint_python` perform still read the tree. Two of those hooks rewrite what they are given (`stage_fixed`), so a commit that touched an upstream skill script would reformat somebody else's code and gate it against rules it was never written for: `eval-viewer/generate_review.py` is 566 lines, which CC001 would fail on the way in but CI's clean-code job never sees. This task draws the line in one place - what the repository owns - and holds the four files that can each draw it separately to the same answer.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The commit hooks never hand `.agents/` to a linter: every command in `lefthook.yml` carries `exclude: ".agents/**"`, and a staged file under the tree is reported as `(skip) no files for inspection` rather than linted.
- [x] #2 The Clean Code gate refuses the tree however the path arrives: `automation/clean_code.py` publishes `VENDORED = (".agents",)`, drops a vendored path named by hand, and widens `.` back to `SCOPE` so the checkout root is not a way to measure it.
- [x] #3 The other two linters agree. `ruff.toml` excludes `.agents` from the whole-checkout run (`ruff check --show-files .` lists none of its 10 Python files) and `biome.json` already excluded it with `!!**/.agents`.
- [x] #4 A test pins the four files to one answer, and each exclusion is worth pinning: removing the Ruff entry or one hook `exclude` fails it.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Why all four, not just the hook.** The hook was the visible symptom, but "what counts as source" is a claim four files make: `automation/clean_code.py` by naming its scope, `lefthook.yml` by its globs, `ruff.toml` by `extend-exclude`, `biome.json` by `files.includes`. Three of them already agreed and one did not, so the fix is the missing line plus a test that the group stays agreed - otherwise the next person renaming a directory re-opens the hole in one place only. `biome check .agents/.../evals.json` already reported "No files were processed (ignored)", so `04-biome` needed the `exclude` only for symmetry; it is inert either way.

**Rude has no exclude setting**, so a scope is the only thing the gate can be told. `command()` still emits `rude check --select CC --format json <paths>` unchanged and `_measured()` decides the paths beforehand: a path inside `VENDORED` is dropped, and `.` or the checkout root becomes `SCOPE`, because handing Rude `.` would read the tree it was told to ignore. The staged path filter in `main()` runs the same check, so `python -m automation.clean_code .agents/...` prints "nothing staged to check" and exits 0 instead of reporting 566-line functions. Nothing else in the gate moved: the thresholds, the rule selection and the parser are untouched.

**Evidence.** `ruff check --show-files .` went from 808 files to 798 - exactly the ten `.agents` Python files, no other file lost - and `ruff format --check .` pass, and `python -m automation.clean_code` reports no findings. The hook was run against the real config with a probe edit staged inside `.agents/skills/skill-creator/eval-viewer/generate_review.py`: `01-ruff-lint` and `03-clean-code` both reported `(skip) no files for inspection`, and the same probe file staged outside the tree (`automation/clean_code.py`) ran all three hooks. `tests/scripts` 382 passed (two new tests), `tests/alint` 23 passed, `apps/docs` 58 pass. The runtime suite is unchanged at 3358 passed / 130 skipped with the same environmental failures of the QGIS-generated `qgis_sdk.processing.*` modules (10 tests plus `test_fake_algorithms`, which cannot import `native` without QGIS installed) - none of them reach a file this change touches.

**Rejected alternatives.** Adding `.agents` to `SCOPE` and letting the gate report on it: the tree is upstream code that this repository does not own, so a finding there is a fix nobody here should make, and the gate would fail on somebody else's 566-line function. Dropping `.agents` from the checkout entirely: AGENTS.md points at those skills on purpose, and `agents:check` verifies the bundle. A `.rudeignore`: Rude has no such setting, which is why the scope is code and not configuration.

**Documentation impact.** No user-facing documentation changes: no package, CLI, wire payload or test assertion moved. `doc-14` gains a paragraph on what the gate measures and `AGENTS.md`'s clean-code rule gains the scope it already had in code, so the two places that explain the gate now say where its edge is; no new decision record, since decision-82 governs the gate and this change only stops it reading a tree that is not this repository's.

<!-- SECTION:NOTES:END -->
