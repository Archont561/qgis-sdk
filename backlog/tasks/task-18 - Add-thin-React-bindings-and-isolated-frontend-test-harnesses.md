---
id: TASK-18
title: Add thin React bindings and isolated frontend test harnesses
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-2
dependencies:
  - TASK-4
  - TASK-17
references:
  - >-
    backlog/decisions/decision-18 -
    Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
priority: medium
type: feature
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add thin React bindings and isolated frontend test harnesses. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Root imports stay framework/browser-global free; vanilla and React consume the same typed client.
- [ ] #2 Provider/remount/dispose tests prove shared connection ownership and no leaked subscriptions.
- [ ] #3 Injected per-client harnesses script typed calls/events/faults, fail unexpected calls and separate mock evidence from native tests.
<!-- AC:END -->
