---
id: TASK-21
title: Implement generation safe development refresh and reconnection
status: In Progress
assignee: []
created_date: 2026-10-16 12:02
updated_date: '2026-10-25T15:34:00Z'
labels: []
milestone: m-3
dependencies:
  - TASK-6
  - TASK-15
  - TASK-4
  - TASK-13
references:
  - >-
    backlog/decisions/decision-15 -
    Refresh-development-through-owned-runtime-generations.md
  - >-
    backlog/decisions/decision-21 -
    Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md
priority: medium
type: feature
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement generation safe development refresh and reconnection. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Preflight errors preserve old revision; post-teardown startup failure cleans partial resources and disables visibly.
- [ ] #2 Serialize/debounce reloads and prevent old-generation delivery; keep frontend HMR separate from Python replacement.
- [ ] #3 Bounded safe-cancellation failure refuses in-process reload and requires explicit restart without killing threads or discarding unsaved state.
<!-- AC:END -->
