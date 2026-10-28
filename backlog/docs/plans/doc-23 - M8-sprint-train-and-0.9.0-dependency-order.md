---
id: doc-23
title: M8 sprint train and 0.9.0 dependency order
type: guide
created_date: '2026-10-26 10:20'
---
# M8 sprint train and 0.9.0 dependency order

**Status:** Planning; the 0.9.0 release follows the TASK-78 gate for 0.8.0.
In 2026-10-28 planning, the owner selected 0.9.0 for worker-first jobs and a
named registry ([decision-65](../../decisions/decision-65%20-%20Run-registered-jobs-on-workers-with-owner-scoped-named-submission.md));
this revises decision-53's planned offloaded-step model. Tasks may start before
the preceding release gate when their declared dependencies permit it. Sprint
membership lives here and in the milestone body. The [session synthesis](doc-28%20-%20Session-synthesis-worker-jobs-API-ergonomics-and-PyQGIS-safety.md)
tracks subsequent API questions and safety findings separately; it does not add
unapproved items to this release gate.

## 1. Where m-8 starts from

Desktop is the only host; `native_plugin_context(iface=None)` builds services
headless; jobs currently run on the driving thread and explicit offloads use
`ThreadPoolWorkers`. The runtime does not yet inject `ctx.jobs`.

| Gap | Owner |
| --- | --- |
| Whole-job worker execution, safe context and migration | [TASK-115](../../tasks/task-115%20-%20Run-whole-jobs-on-workers-with-a-restricted-context.md) |
| Jobs invisible to the QGIS task bar; a second pool beside the task manager | [TASK-82](../../tasks/task-82%20-%20Run-offloaded-job-steps-as-QgsTasks-under-QgsTaskManager-with-the-job-visible-as-a-parent-task.md) |
| Named scoped submission, actions and view/request ownership | [TASK-116](../../tasks/task-116%20-%20Expose-owner-scoped-named-jobs-and-action-handles.md) |
| Source-only worker safety diagnostics | [TASK-117](../../tasks/task-117%20-%20Check-worker-job-safety-with-source-only-lint-rules.md) |
| No server lifecycle, filters, services or access control | [TASK-80](../../tasks/task-80%20-%20Add-the-QGIS-Server-host-server-declarations-ServerContext-generated-serverClassFactory-in-process-QgsServer-tests-and-dev-host-server.md) |
| No application lifecycle, `qgis-sdk run` or app packaging target | [TASK-81](../../tasks/task-81%20-%20Add-the-standalone-app-host-qgis_sdk.app.run-an-optional-canvas-window-qgis-sdk-run-and-build-target-app.md) |

## 2. Dependency read

| Task | Declared dependencies | Startable |
| --- | --- | --- |
| TASK-115 worker-first execution | TASK-58 | after 0.6.0 |
| TASK-82 task-manager workers | TASK-58, TASK-115 | after worker contract |
| TASK-116 named registry and actions | TASK-115, TASK-67 | after worker contract |
| TASK-117 job lint | TASK-115, TASK-116 | after registry |
| TASK-80 server host | TASK-64, TASK-63, TASK-116 | after registry |
| TASK-81 app host | TASK-64, TASK-67, TASK-116 | after registry |
| [TASK-83](../../tasks/task-83%20-%20Prepare-and-qualify-0.9.0-release.md) 0.9.0 gate | TASK-78, 80, 81, 82, 115, 116, 117 | release gate |

## 3. Sprint train

- **Sprint 1: TASK-115.** Worker-first execution, restricted context, delivery,
  cancellation and async/offload migration. The full job body runs on workers.
- **Sprint 2: TASK-82 and TASK-116** may proceed after TASK-115. TASK-82 uses
  one `QgsTask` per job and keeps task-manager dependencies and cooperative
  cancellation; TASK-116 delivers the named registry, actions and owner scopes.
  TASK-82's historical filename/title describes the old step model; its revised
  description and criteria are authoritative.
- **Sprint 3: TASK-117.** Source-only worker-safety lint; static checks are not
  a thread-safety proof. TASK-80 and TASK-81 may start once TASK-116 is ready.
- **Sprints 4–5: TASK-80 then TASK-81.** Server and app hosts, integrated with
  request/view/plugin ownership and the new registry.
- **Gate: TASK-83.** Python-only `python-v0.9.0`, with migration evidence and a
  verified zero bridge delta. A changed wire needs a separate contract/version
  decision; release requires explicit authorization.

## 4. Hygiene at sprint start

- Follow decision-65's amendments to decisions 13, 38 and 53; preserve
  decision-21's cooperative cancellation and reload safety.
- Re-measure the baseline; record the Windows row for `qgis-sdk run` or its
  blocker (TASK-33). Do not bump release manifests during planning.
