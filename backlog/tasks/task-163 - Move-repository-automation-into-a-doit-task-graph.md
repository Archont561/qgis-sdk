---
id: TASK-163
title: Move repository automation into a doit task graph
status: In Progress
assignee: []
created_date: '2026-11-09 23:20'
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
