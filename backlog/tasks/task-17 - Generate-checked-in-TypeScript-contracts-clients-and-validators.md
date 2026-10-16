---
id: TASK-17
title: Generate checked in TypeScript contracts clients and validators
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-2
dependencies:
  - TASK-2
  - TASK-12
references:
  - >-
    backlog/decisions/decision-10 -
    Use-dataclass-authoring-and-schema-driven-TypeScript-generation.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
priority: medium
type: feature
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Generate checked in TypeScript contracts clients and validators. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Generate deterministic DTOs/operation maps/events/clients from Python without running QGIS or handlers.
- [ ] #2 Compile-time tests reject invalid names/arguments; runtime tests reject malformed responses with asymmetric additive compatibility.
- [ ] #3 Unsupported annotations fail rather than emit any; CI drift checks protect generated-file ownership.
<!-- AC:END -->
