---
id: TASK-15
title: Implement scoped local jobs and typed result handles
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 17:02'
labels: []
milestone: m-2
dependencies:
  - TASK-13
  - TASK-24
references:
  - >-
    backlog/decisions/decision-13 -
    Use-runtime-bound-Celery-inspired-local-jobs.md
  - >-
    backlog/decisions/decision-21 -
    Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md
priority: medium
type: feature
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement scoped local jobs and typed result handles. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Provide runtime-bound submission, progress, result/error/cancellation and explicit lifetime semantics.
- [ ] #2 View disposal detaches callbacks and requests cancellation; hiding does not dispose; plugin lifetime is explicit.
- [ ] #3 Stateful tests cover races/stuck work and acknowledge cancellation; no automatic retries initially.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 16:54
---
Moved from m-1 to m-2 on 2026-10-24 during the 0.2.0 re-scope, for the same reasons as TASK-5: nothing in m-1 depends on it, it is not part of the 'native runtime and Processing' surface 0.2.0 is named for, and its job transport still rests on decision-13, which is only proposed. TASK-29 gates 0.3.0 on it.
---

author: qgis-sdk agent
created: 2026-10-24 17:02
---
decision-13 is now accepted (2026-10-24): submission is ctx.jobs.bind(JobClass).delay(inputs) - the delay(JobClass, inputs) alternative is dropped - and late subscribers replay the current state as one synthetic transition, with disposal beating replay. decision-21 still sets the scope: view-owned by default, no automatic retries, cancellation is a request until acknowledged. Implement to that; do not redesign it here.
---
<!-- COMMENTS:END -->
