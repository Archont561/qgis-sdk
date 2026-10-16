---
id: TASK-13
title: Prove Qt compatible coroutine scheduling and safe cancellation
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-0
dependencies:
  - TASK-23
references:
  - >-
    backlog/decisions/decision-4 -
    QGIS-aware-networking-uses-an-async-first-transport.md
  - >-
    backlog/decisions/decision-21 -
    Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
priority: high
type: spike
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Prove Qt compatible coroutine scheduling and safe cancellation. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Demonstrate sync/async GUI responsiveness and correct thread handoff on candidate target runtimes.
- [ ] #2 Test cancellation, disposal, stuck work and late callbacks with reproducible results.
- [ ] #3 A failed spike triggers explicit scope review rather than a silent API downgrade.
<!-- AC:END -->
