---
id: TASK-12
title: Evaluate dataclass validation and TypeScript generation backends
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
labels: []
milestone: m-0
dependencies: []
references:
  - >-
    backlog/decisions/decision-10 -
    Use-dataclass-authoring-and-schema-driven-TypeScript-generation.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
priority: high
type: spike
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evaluate dataclass validation and TypeScript generation backends. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compare apischema and TypeAdapter on strict requests, defaults/nullability, unions and separate input/output schemas.
- [ ] #2 Exercise candidate Python/QGIS compatibility and generated TS/runtime-validator consistency.
- [ ] #3 Record a recommendation and blockers under pure-Python-first packaging; native requirements need explicit reconsideration.
<!-- AC:END -->
