---
id: TASK-24
title: Implement scoped plugin runtime and native lifecycle adapter
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-1
dependencies:
  - TASK-2
  - TASK-11
  - TASK-23
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - >-
    backlog/decisions/decision-12 -
    Use-one-context-injected-controller-per-UI-surface.md
  - >-
    backlog/decisions/decision-21 -
    Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md
priority: medium
type: feature
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement scoped plugin runtime and native lifecycle adapter. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Construct plain author classes through explicit context/factories without constructor rewriting.
- [ ] #2 Own/dispose actions, signals, dialogs/docks and work; repeated unload and partial startup failure are safe.
- [ ] #3 Provide focused pure lifecycle tests and real Desktop startup/unload evidence with no fake fallback.
<!-- AC:END -->
