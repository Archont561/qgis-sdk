---
id: TASK-14
title: Implement class based Processing algorithms and safe outputs
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-1
dependencies:
  - TASK-24
  - TASK-25
references:
  - >-
    backlog/decisions/decision-11 -
    Use-one-context-injected-class-per-Processing-algorithm.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
priority: medium
type: feature
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement class based Processing algorithms and safe outputs. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Inspect one decorated plain class/run entry point and construct fresh execution context per invocation.
- [ ] #2 Map typed parameters/results with explicit projected CRS/units and non-destructive output semantics.
- [ ] #3 Pure and real Processing tests prove source preservation, cleanup and GUI-side project addition after success.
<!-- AC:END -->
