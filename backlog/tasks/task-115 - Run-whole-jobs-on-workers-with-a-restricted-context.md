---
id: TASK-115
title: Run whole jobs on workers with a restricted context
status: To Do
assignee: []
created_date: '2026-10-28 14:47'
updated_date: '2026-10-28 16:24'
labels: []
milestone: m-8
dependencies:
  - TASK-58
type: enhancement
ordinal: 115000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement the worker-first job execution contract for 0.9.0, as recorded in the new worker-first jobs decision. A synchronous @job body runs in its entirety on a worker through the Workers seam; the driving thread manages submission and delivery. This is a breaking change from the current driving-thread/explicit-offload model, not an implicit switch of an existing coroutine onto a worker. Keep the plain-function declaration and owner-bound service model. TASK-82 supplies the native QgsTaskManager adapter.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A submitted synchronous job never executes its body on the driving thread; a real worker thread test records distinct thread identities and proves the GUI/event loop remains responsive. No worker backend means a clear submission failure, never silent driving-thread execution.
- [ ] #2 A fresh restricted worker context exposes thread-safe cancellation and progress, not live GUI/project/iface services; reject unsupported declarations and unsafe context access clearly. Validate typed inputs before scheduling and typed results on delivery; document that static validation is not a sandbox.
- [ ] #3 Progress, success, failure and cancellation are marshalled to the driving/GUI thread, including late-subscriber replay; owner disposal wins over queued or replayed callbacks and concurrent views remain isolated.
- [ ] #4 Cancellation remains cooperative: queued and running cancellation races, acknowledged cancellation versus successful completion, and quiesce/reload with stuck work have deterministic and native coverage; no worker is killed and no resource is freed under active work.
- [ ] #5 Decide and implement a clear 0.9 migration for existing async @job functions and driving-thread capabilities: either explicitly supported without violating the worker-first contract or refused with actionable migration guidance; update guides and tests, never silently retain old execution semantics.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Session follow-up: the owner also wants third-party-friendly job dependency injection and easy fake overrides; TASK-122 explores that separately after the worker contract. No Depends API exists and no 0.9.0 DI commitment has been made.

Ecosystem research: TASK-131 explores deterministic bounded job test helpers with progress, cooperative cancellation and native/worker evidence; it does not change the accepted 0.9 contract.
<!-- SECTION:NOTES:END -->
