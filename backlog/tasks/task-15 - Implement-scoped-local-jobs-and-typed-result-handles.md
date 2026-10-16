---
id: TASK-15
title: Implement scoped local jobs and typed result handles
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-1
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
