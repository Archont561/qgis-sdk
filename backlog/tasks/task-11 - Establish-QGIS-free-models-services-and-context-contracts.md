---
id: TASK-11
title: Establish QGIS free models services and context contracts
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
labels: []
milestone: m-0
dependencies: []
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - >-
    backlog/decisions/decision-14 -
    Enforce-QGIS-free-import-boundaries-during-check.md
priority: medium
type: feature
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Establish QGIS free models services and context contracts. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Enforce models/services/core dependency direction and native-import isolation with pure import tests.
- [ ] #2 Specify plugin/UI/algorithm/job scoped typed contexts and fake-service seams without global registration.
- [ ] #3 Document typed errors, lifecycle ownership and explicit unsupported/native capabilities.
<!-- AC:END -->
