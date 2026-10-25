---
id: TASK-16
title: Implement non mutating check and QGIS import diagnostics
status: In Progress
assignee: []
created_date: 2026-10-16 12:02
updated_date: '2026-10-25T11:32:00Z'
labels: []
milestone: m-3
dependencies:
  - TASK-2
  - TASK-11
  - TASK-12
references:
  - >-
    backlog/decisions/decision-8 -
    Separate-check-test-dev-and-build-workflows.md
  - >-
    backlog/decisions/decision-14 -
    Enforce-QGIS-free-import-boundaries-during-check.md
priority: medium
type: feature
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement non mutating check and QGIS import diagnostics. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Validate source metadata/declarations/assets/dependency policy without native imports, installs or handler execution.
- [x] #2 AST and blocked-import tests cover eager module/class/conditional imports, narrow native exemptions and TYPE_CHECKING.
- [ ] #3 Stable diagnostics and shared checking APIs are reused by build with no source mutation.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Started 2026-10-25 as m-3 sprint 1 (doc-16). First slice: qgis_sdk.check library (QGIS001 import-time native imports with class scope, try/except, conditional blocks and TYPE_CHECKING; metadata.txt presence and required keys), the check command receiving its runtime through ctx.obj (decision-34, CliRuntime in qgis_sdk.cli, FakeCliRuntime in qgis_sdk.testing), and the acceptance that a project from qgis-sdk new passes check clean.

First slice landed (session arena/cb8f8577): qgis_sdk.check (Diagnostic/CheckReport, check_source with QGIS001 + ARCH001 + SYNTAX001, check_project with META001-003, PROJECT001, CONFIG001, pyproject [tool.qgis-sdk.check] native-modules), qgis_sdk.cli.CliRuntime + qgis_sdk.testing.FakeCliRuntime, qgis-sdk check [PATH] [--native ...] [--json] (exit 1 on errors, 2 when not a directory). Tests: test_check_imports.py, test_check_project.py, test_check_cli.py; the scaffold passes check clean. AC #2 satisfied. AC #1 still open for declarations/assets/dependency policy; AC #3 waits for build (TASK-21) to call check_project in-process. decision-14 stays proposed until build consumes the diagnostics.
<!-- SECTION:NOTES:END -->
