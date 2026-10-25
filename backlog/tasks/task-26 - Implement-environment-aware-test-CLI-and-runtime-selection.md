---
id: TASK-26
title: Implement environment aware test CLI and runtime selection
status: Done
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-25 13:27'
labels: []
milestone: m-3
dependencies:
  - TASK-7
  - TASK-23
references:
  - >-
    backlog/decisions/decision-7 -
    Use-layered-pytest-fixtures-properties-and-behavioural-contracts.md
  - >-
    backlog/decisions/decision-8 -
    Separate-check-test-dev-and-build-workflows.md
  - >-
    backlog/decisions/decision-18 -
    Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md
priority: medium
type: feature
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement environment aware test CLI and runtime selection. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Forward pytest arguments/output/exit code while keeping direct pytest usage supported.
- [x] #2 Pure collection avoids native imports; explicitly requested missing native runtimes fail instead of skipping green.
- [x] #3 Isolate temporary profiles/processes and expose generated Vitest workflows with clear runtime diagnostics.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delivered in PR #71 (sprint 2, doc-16). `qgis-sdk test [PYTEST_ARGS]... [--project] [--target pure|qgis|desktop|web] [--qgis-prefix]` plans a process over `qgis_sdk.devtools.testrun.plan_tests` and runs it through the CLI runtime; pytest arguments, output and exit code pass through, and a plain `pytest` loads the same `qgis_sdk.pytest_plugin` via the scaffold's addopts (AC #1). The pure target deselects `qgis`/`desktop` and fails any test that imports qgis/PyQt/PySide; a native target with no QGIS found exits 2 naming what was tried (never a download), and a native selection that only skipped exits 1 (AC #2). Desktop runs pytest inside the QGIS binary with a per-run temporary profile that is removed afterwards; `--target web` runs the project's Vitest through the package manager its lockfile names; each plan prints its runtime note (prefix, source, python/executable, offscreen or on screen) to stderr (AC #3). Evidence: unit tests on plans with FakeCliRuntime, plus the opt-in `QGIS_SDK_DEVTOOLS=1` harness (tests/test_devtools_native.py) against QGIS 4.2.3 - all targets, a failing desktop test, an all-skipped gate; recorded in doc-14.
<!-- SECTION:NOTES:END -->
