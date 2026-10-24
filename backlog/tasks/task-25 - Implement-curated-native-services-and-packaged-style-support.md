---
id: TASK-25
title: Implement curated native services and packaged style support
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 14:15'
labels: []
milestone: m-1
dependencies:
  - TASK-24
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - >-
    backlog/decisions/decision-16 -
    Separate-reusable-layer-styles-from-UI-themes.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - >-
    backlog/tasks/task-38 -
    Epic-v2-0.2.0-native-runtime-and-Processing-algorithms.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
priority: medium
type: feature
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement curated native services and packaged style support. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Provide typed layer/project/notification/settings contracts with matching fake/native tests for real workflows.
- [ ] #2 Validate layer lifetime, selection, output ownership and scoped resource operations without mirroring all PyQGIS.
- [ ] #3 Apply reviewed packaged QML to compatible outputs and inherit native UI theme without global stylesheet mutation.
<!-- AC:END -->
