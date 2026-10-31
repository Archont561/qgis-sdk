---
id: TASK-82
title: >-
  Run offloaded job steps as QgsTasks under QgsTaskManager with the job visible
  as a parent task
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-30 13:20'
labels: []
milestone: m-8
dependencies:
  - TASK-58
  - TASK-115
type: enhancement
ordinal: 82000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Adapt the native Workers seam to QgsTaskManager for the worker-first job contract in decision-65, replacing the superseded offload-step plan in decision-53. The whole job body runs inside one QgsTask, visible with its title, progress and cancellation; the driving-thread handoff owns outcome delivery. Retire ThreadPoolWorkers from native composition (keep pure fakes). Preserve task-manager dependencies via ctx.jobs.after(handle), cooperative cancellation, view/request ownership, reload quiescence and Processing not being wrapped twice. The original task title records the previous step-based plan; it no longer describes the execution model.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A synchronous job runs wholly in a QgsTask under QgsApplication.taskManager(), appears as one task with its title, progress and cancellation, and delivers callbacks on the driving thread; native tests prove worker versus GUI thread identities and responsiveness.
- [x] #2 A dependency declared with ctx.jobs.after runs only after its prerequisite finishes; view or request disposal requests cancellation; reload waits for acknowledgement or refuses replacement. Exercise races on deterministic fakes and natively.
- [x] #3 ThreadPoolWorkers is removed from native composition and the services harness passes on the task-manager adapter; no GUI work runs inside QgsTask.run(), and Processing is not wrapped twice.
- [x] #4 Document task-bar behavior and the 0.9 migration from driving-thread async jobs and explicit offload; update the affected decision status reviews and native tests without claiming unchanged scheduler thread-affinity semantics.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lifetime defect found and fixed at the 0.9.0 gate (2026-10-31). `QgsTaskManager.addTask` takes ownership of the task, and the manager keeps working with it after `finished()` returns - it posts `processSubTasksForCompletion`, emits the completion progress the task bar draws, then deletes the task. `QgsTaskWorkers` dropped its last Python reference *inside* `finished()`, so the sip object was deleted under the manager's feet; the whole suite then died with `Fatal Python error: Segmentation fault` inside `QgsTaskManager::progressChanged` in 3 of 4 runs of one job and 1 of 2 of another. The failure was intermittent (conda-forge's locked environment, QGIS 4.2.3 / Qt 6 / CPython 3.14) and first surfaced as a red `autorelease` quality gate, not as a CI test failure, because only the release gate runs the whole suite in one process. `_JobTask.finished()` now drops the body's closure, stops mirroring progress and calls `deleteLater()`; `QgsTaskWorkers` retires the wrapper and releases it only from its own stack (`offload`, `_forget`, the `tasks` and `retired` reads) after Qt's `destroyed` reports the C++ object gone, never from inside a Qt callback. Twelve consecutive whole-suite runs after the fix were green (6 + 6, ~2609 passed each). A native regression test, `test_a_finished_task_outlives_its_own_completion_callback`, pins the rule: nothing is freed in `finished()`, and `retired` returns to zero once Qt deletes the task. The `progressChanged` probe in `test_progress_reported_by_the_body_reaches_the_task` is now disconnected in a `finally` - a connection to the application's singleton task manager outlived its module.
<!-- SECTION:NOTES:END -->
