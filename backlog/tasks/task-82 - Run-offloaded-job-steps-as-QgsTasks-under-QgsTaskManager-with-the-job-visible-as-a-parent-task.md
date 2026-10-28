---
id: TASK-82
title: >-
  Run offloaded job steps as QgsTasks under QgsTaskManager with the job visible
  as a parent task
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-28 14:48'
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
- [ ] #1 A synchronous job runs wholly in a QgsTask under QgsApplication.taskManager(), appears as one task with its title, progress and cancellation, and delivers callbacks on the driving thread; native tests prove worker versus GUI thread identities and responsiveness.
- [ ] #2 A dependency declared with ctx.jobs.after runs only after its prerequisite finishes; view or request disposal requests cancellation; reload waits for acknowledgement or refuses replacement. Exercise races on deterministic fakes and natively.
- [ ] #3 ThreadPoolWorkers is removed from native composition and the services harness passes on the task-manager adapter; no GUI work runs inside QgsTask.run(), and Processing is not wrapped twice.
- [ ] #4 Document task-bar behavior and the 0.9 migration from driving-thread async jobs and explicit offload; update the affected decision status reviews and native tests without claiming unchanged scheduler thread-affinity semantics.
<!-- AC:END -->
