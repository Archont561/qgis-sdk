---
id: doc-23
title: M8 sprint train and 0.9.0 dependency order
type: guide
created_date: '2026-10-26 10:20'
---
# M8 sprint train and 0.9.0 dependency order

**Status:** Planning; starts after the TASK-78 gate closes 0.8.0 (sprint 1
may start earlier, it depends only on 0.6.0's `@job`). Orders work the m-8
tasks already declare; adds no scope. Sprint membership lives here and in the
milestone body ([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

## 1. Where m-8 starts from

Desktop is the only host; `native_plugin_context(iface=None)` already builds
every service headless; `ThreadPoolWorkers` runs offloaded steps. Gaps and
owners ([decision-52](../../decisions/decision-52%20-%20Run-one-plugin-class-on-three-hosts-QGIS-Desktop-QGIS-Server-and-standalone-PyQGIS-apps.md), [decision-53](../../decisions/decision-53%20-%20Run-offloaded-job-steps-as-QgsTasks-under-QgsTaskManager-and-keep-the-step-scheduler-on-the-driving-thread.md)):

| Gap | Owner |
| --- | --- |
| Jobs invisible to the QGIS task bar; a second thread pool beside the task manager | **TASK-82** |
| No server lifecycle, filters, services or access control; no in-process `QgsServer` tests | **TASK-80** |
| No application lifecycle, no `qgis-sdk run`, no app packaging target | **TASK-81** |

## 2. Dependency read

| Task | Declared dependencies | Startable |
| --- | --- | --- |
| [TASK-82](../../tasks/task-82%20-%20Run-offloaded-job-steps-as-QgsTasks-under-QgsTaskManager-with-the-job-visible-as-a-parent-task.md) task-manager workers | TASK-58 ✓ | now |
| [TASK-80](../../tasks/task-80%20-%20Add-the-QGIS-Server-host-server-declarations-ServerContext-generated-serverClassFactory-in-process-QgsServer-tests-and-dev-host-server.md) server host | TASK-64, TASK-63 | after 0.6.0 |
| [TASK-81](../../tasks/task-81%20-%20Add-the-standalone-app-host-qgis_sdk.app.run-an-optional-canvas-window-qgis-sdk-run-and-build-target-app.md) app host | TASK-64, TASK-67 | after 0.6.0 |
| [TASK-83](../../tasks/task-83%20-%20Prepare-and-qualify-0.9.0-release.md) 0.9.0 gate | TASK-78, 80, 81, 82 | release gate |

## 3. Sprint train

- **Sprint 1: TASK-82.** `QgsTask` subclass per offload, parent task per
  job, `ctx.jobs.after`, `ThreadPoolWorkers` retired natively; the
  scheduler's thread-affinity properties are the regression net. Smallest
  slice; it de-risks the thread model the server and app hosts inherit.
- **Sprint 2: TASK-80.** `hosts`, server declarations and `ServerContext`,
  generated `serverClassFactory`, HOST001/HOST002, in-process `QgsServer`
  runner for `test --target server`, `dev --host server`, scaffold and
  example variants.
- **Sprint 3: TASK-81.** `qgis_sdk.app.run`, the canvas window for
  `gui=True`, `qgis-sdk run`, `build --target app`, the app entry in the
  example.
- **Gate: TASK-83.** Python-only `python-v0.9.0`; the zero bridge delta
  shown, not assumed. Only on an explicit "Release 0.9.0".

## 4. Hygiene at sprint start

- decision-13 and decision-21 status reviews naming the task-manager
  adapter (written with TASK-82).
- Re-measure the baseline; record the Windows row for `qgis-sdk run` or its
  blocker (TASK-33).
