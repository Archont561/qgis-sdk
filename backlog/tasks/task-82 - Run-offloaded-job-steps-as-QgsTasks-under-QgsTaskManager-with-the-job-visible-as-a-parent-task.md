---
id: TASK-82
title: >-
  Run offloaded job steps as QgsTasks under QgsTaskManager with the job visible
  as a parent task
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-8
dependencies:
  - TASK-58
type: enhancement
ordinal: 82000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-53. A QgsTask subclass per offload(fn) added to QgsApplication.taskManager(), reporting through the existing Handoff so the StepScheduler, ownership and JobContext stay unchanged; a parent QgsTask per job mirroring title, progress and cancel through the CancellationToken; offloaded steps as sub-tasks; ctx.jobs.after(handle) dependencies enforced by the manager; ThreadPoolWorkers retired from the native composition (fakes stay); no GUI-thread step runs inside QgsTask.run(); Processing algorithms are not wrapped twice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A job with three offloaded steps appears as one task with sub-tasks in QgsApplication.taskManager(), its progress mirrors ctx.progress, cancelling it from the manager ends the job through the token, and author steps still resume on the driving thread (qgis native tests; the scheduler's thread-affinity properties unchanged).
- [ ] #2 A dependency declared with ctx.jobs.after runs only after its prerequisite finished; a view-owned job is cancelled when its view is disposed; reload quiesces and waits as before (stateful tests on the fakes + native).
- [ ] #3 ThreadPoolWorkers is removed from adapters/qgis and the services harness passes on the task-manager adapter; decision-13 and decision-21 carry status reviews; doc-12 documents what users see in the task bar.
<!-- AC:END -->
