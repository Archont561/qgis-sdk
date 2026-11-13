---
id: TASK-163
title: Move repository automation into a doit task graph
status: Done
assignee: []
created_date: '2026-11-09 23:20'
updated_date: '2026-11-13 09:15'
labels: []
dependencies: []
ordinal: 163000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/*.py are four standalone scripts invoked by 35 one-line Pixi tasks, and every workflow step spells the command out again. Move the Python into an importable automation/ package, declare the tasks in dodo.py, and make pixi run automation <task> the one front door, with Pixi keeping only the environment primitives.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 automation/ holds ci, release, results and commits as importable modules; scripts/ no longer contains Python automation.
- [x] #2 dodo.py declares every task with a docstring and parameters; pixi run automation list is the vocabulary and pixi run automation check runs the fast gates.
- [x] #3 Pixi keeps only environment primitives and pins doit exactly in feature.python.
- [x] #4 Every workflow runs gates through pixi run automation <task>; harness verbs stay python -m automation.ci because they wrap an arbitrary command.
- [x] #5 A guard test fails when a workflow names an undeclared task, a task lacks a docstring, dodo.py calls a missing function, or an automation module imports doit.
- [x] #6 doc-14, docs/development, AGENTS.md and the skills show the new commands; no document keeps a command that no longer exists outside a historical record.
<!-- AC:END -->

## Evidence

- `tests/scripts`: 321 passed (310 before, 11 new in `test_automation_cli.py`).
- `doit list` lists 41 tasks with their docstrings; `doit release_verify_versions`
  and `doit release_plan --dry-run true` ran green through the registry.
- ruff check and format clean over 539 files, markdownlint 0 issues, biome 214
  files, Alint 9/9 rules.
- The site rebuilds with 77 decision records and 9308 internal links, 0 broken.
- `pixi.lock` gains `doit-0.37.0` for `default` and `build` in the relock commit
  the `relock` job pushed (`b798c4b`); the first pull-request run failed on
  `locked: true` before that.
