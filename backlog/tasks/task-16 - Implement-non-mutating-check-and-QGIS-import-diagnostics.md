---
id: TASK-16
title: Implement non mutating check and QGIS import diagnostics
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
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
- [ ] #2 AST and blocked-import tests cover eager module/class/conditional imports, narrow native exemptions and TYPE_CHECKING.
- [ ] #3 Stable diagnostics and shared checking APIs are reused by build with no source mutation.
<!-- AC:END -->
