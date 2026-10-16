---
id: TASK-4
title: Add the versioned WebEngine bridge contract
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-2
dependencies:
  - TASK-2
  - TASK-17
  - TASK-20
  - TASK-24
  - TASK-14
  - TASK-15
  - TASK-5
references:
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
priority: medium
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Integrate the versioned optional bridge with the dedicated code-generation, security and runtime tasks. Preserve all existing IPC/stream/resource acceptance criteria; raw native objects never cross the boundary.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Python and TypeScript validate the same contract fixtures.
- [ ] #2 Bridge surface is allowlisted and serializable; raw Qt/QGIS objects and arbitrary Python invocation are not exposed.
- [ ] #3 Bridge behavior can be tested without relying on live external services.
- [ ] #4 Generated operation-specific clients reject unknown operations and invalid inputs at compile time and validate responses at runtime; a manually asserted invoke<T> is not the public type-safety guarantee.
- [ ] #5 All calls pass through a narrow dispatcher with trusted host-bound view/origin/generation; forged payload caller IDs and direct-object paths cannot bypass per-view/resource authorization.
- [ ] #6 Invocation replies, subscriptions and operation streams have tested ordering, terminal/disposal/reconnect semantics and documented bounded buffering, gap/overflow policy and progress coalescing where applicable.
- [ ] #7 Resource release distinguishes borrowed layer handles from subscriptions and owned temporary outputs; releasing a borrowed handle never deletes the project layer, and repeated/in-flight close behavior is tested.
- [ ] #8 Client-local injected transports support typed scripted handlers, faults/events, isolated clients and leak checks; local abort/timeout is distinct from acknowledged host cancellation and never causes automatic unknown-outcome retries.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Tauri source review (2026-10-16): follow proposed decision-23 and doc-2 section 10. Verify native caller binding/QWebChannel behavior separately from mock tests. Public API names, stream limits and cancellation wire details remain open; no implementation is complete.
<!-- SECTION:NOTES:END -->
