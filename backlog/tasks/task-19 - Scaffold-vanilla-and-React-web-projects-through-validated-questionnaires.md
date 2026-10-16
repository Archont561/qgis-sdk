---
id: TASK-19
title: Scaffold vanilla and React web projects through validated questionnaires
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-3
dependencies:
  - TASK-1
  - TASK-18
  - TASK-17
references:
  - >-
    backlog/decisions/decision-18 -
    Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
priority: medium
type: feature
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scaffold vanilla and React web projects through validated questionnaires. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Interactive and no-input flags share one validated generation plan for vanilla/React, dialog/dock and npm/pnpm/Bun.
- [ ] #2 Vite apps and Vitest tests work with selected package managers; Bunup remains library tooling.
- [ ] #3 Dependency install is opt-in; controlled templates validate names/collisions, preserve files on install failure and include checked-in bindings.
<!-- AC:END -->
