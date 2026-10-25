---
id: TASK-26
title: Implement environment aware test CLI and runtime selection
status: In Progress
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-25 13:14'
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
- [ ] #1 Forward pytest arguments/output/exit code while keeping direct pytest usage supported.
- [ ] #2 Pure collection avoids native imports; explicitly requested missing native runtimes fail instead of skipping green.
- [ ] #3 Isolate temporary profiles/processes and expose generated Vitest workflows with clear runtime diagnostics.
<!-- AC:END -->
