---
id: TASK-115
title: Run whole jobs on workers with a restricted context
status: Done
assignee: []
created_date: '2026-10-28 14:47'
updated_date: '2026-10-30 12:40'
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
- [x] #1 A submitted synchronous job never executes its body on the driving thread; a real worker thread test records distinct thread identities and proves the GUI/event loop remains responsive. No worker backend means a clear submission failure, never silent driving-thread execution.
- [x] #2 A fresh restricted worker context exposes thread-safe cancellation and progress, not live GUI/project/iface services; reject unsupported declarations and unsafe context access clearly. Validate typed inputs before scheduling and typed results on delivery; document that static validation is not a sandbox.
- [x] #3 Progress, success, failure and cancellation are marshalled to the driving/GUI thread, including late-subscriber replay; owner disposal wins over queued or replayed callbacks and concurrent views remain isolated.
- [x] #4 Cancellation remains cooperative: queued and running cancellation races, acknowledged cancellation versus successful completion, and quiesce/reload with stuck work have deterministic and native coverage; no worker is killed and no resource is freed under active work.
- [x] #5 Decide and implement a clear 0.9 migration for existing async @job functions and driving-thread capabilities: either explicitly supported without violating the worker-first contract or refused with actionable migration guidance; update guides and tests, never silently retain old execution semantics.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Session follow-up: the owner also wants third-party-friendly job dependency injection and easy fake overrides; TASK-122 explores that separately after the worker contract. No Depends API exists and no 0.9.0 DI commitment has been made.

Ecosystem research: TASK-131 explores deterministic bounded job test helpers with progress, cooperative cancellation and native/worker evidence; it does not change the accepted 0.9 contract.
2026-10-30 (implemented): the contract is in place and the suite is green.

Runtime. `qgis_sdk.core.WorkerContext` is the context a body receives: `progress` and `cancellation` only, assembled once, and every driving-thread name (`algorithms`, `files`, `iface`, `layers`, `network`, `notifications`, `project`, `scope`, `ui`, `view`, `workers`) refuses by name with `QgisSdkUnsupportedCapabilityError(capability, reason)` carrying the sentence that says why. `describe_job` refuses `async def` and `ctx: JobContext` with migration text and requires `WorkerContext`; `JobDescription.asynchronous` is always `False` but stays in the transport form so a 0.8 reader still parses one. `JobService._submit` raises `QgisSdkJobRejectedError` when the host has no worker backend - never a quiet return to driving-thread execution. `_run_attempt` builds a fresh `WorkerContext` per attempt, hands `lambda: function(context, **arguments)` to `Workers.offload`, validates the result type on the driving thread before any subscriber sees it, and never calls the body itself. `tick()` and `quiesce()` are driving-thread only: `tick()` returns 0 and `quiesce()` refuses with the named blocker off that thread. `JobHandle.cancel()` sets the attempt's `threading.Event`, which is what a worker polls through `ctx.cancellation.is_cancelled()`, and the progress service is a lock-guarded latest-wins slot delivered on the next tick (a burst from a worker coalesces to one fraction).

Cancellation semantics, decided while implementing: a request that arrives before the worker reports settles the attempt at that report, so a body that ignores the request and returns still ends `cancelled` rather than publishing a result nobody waits for; the pool adapter keeps reporting `QgisSdkJobCancelledError` for a callable it never started, and nothing interrupts a thread. That is decision-21's safety rule preserved under worker-first, and it is what the scheduler's existing cancellation-at-the-suspension rule already did for offloaded work.

Evidence. Python suite 2171 passed / 59 skipped / 7 deselected offscreen; coverage 95.38 % (gate 90). `tests/test_jobs.py` was rewritten for the three-move drive (tick submits, the worker runs, tick delivers) - 57 tests including AC1's real-thread cases over `qgis_sdk.testing.ThreadWorkers` (distinct thread identities, the tick returning while the body still runs, callbacks back on the driving thread, a cooperative poll seeing the request, the backend told exactly once). `tests/test_jobs_native.py` drives the same service over a real `QThreadPool` and a QTimer on a real event loop. `tests/test_jobs_properties.py` keeps the Hypothesis state machine, now running worker reports on a thread of its own so a body that reaches for the tick is refused instead of given a nested one. The BDD feature was restated for worker-first (10 scenarios). `tests/test_contexts.py` gained the WorkerContext refusal matrix. `tests/test_jobs_bdd/_functions/_properties`, `test_quiesce`, `test_surfaces_native`, `test_ui_context`, `ui_component_contract`, `test_describe` and `devtools/exercise.py` were migrated; `qgis-sdk dev`'s stuck-job exercise now blocks inside the body on a real pool thread.

Docs. doc-12's "Scoped jobs" section describes the worker-first contract, the three-move drive and a new "Migrating a 0.8 job to 0.9" subsection covering the context, GUI preparation before submission, GUI updates in subscribers, cooperative cancellation and hosts without a backend. The consolidated 0.9.0 release notes stay with TASK-83.

Not claimed here: TASK-82's native `QgsTaskManager` backend (the pool adapter is still a `QThreadPool`), which is the next task in the milestone order.

<!-- SECTION:NOTES:END -->
