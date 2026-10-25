---
id: TASK-21
title: Implement generation safe development refresh and reconnection
status: Done
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-25 16:30'
labels: []
milestone: m-3
dependencies:
  - TASK-6
  - TASK-15
  - TASK-4
  - TASK-13
references:
  - >-
    backlog/decisions/decision-15 -
    Refresh-development-through-owned-runtime-generations.md
  - >-
    backlog/decisions/decision-21 -
    Bound-job-ownership-and-refuse-unsafe-runtime-replacement.md
priority: medium
type: feature
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement generation safe development refresh and reconnection. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Preflight errors preserve old revision; post-teardown startup failure cleans partial resources and disables visibly.
- [x] #2 Serialize/debounce reloads and prevent old-generation delivery; keep frontend HMR separate from Python replacement.
- [x] #3 Bounded safe-cancellation failure refuses in-process reload and requires explicit restart without killing threads or discarding unsaved state.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Landed in session arena/7a0272e6 (sprint 3, doc-16). Runtime: ResourceScope.on_quiesce/quiesce/resume, PluginRuntime.quiesce/resume, root JobService registers on its scope and names blockers by handle id (tests/test_quiesce.py). Tools: qgis_sdk_tools.devtools.reloader (ReloadCoordinator: preflight = compile + check_project, bounded 2 s quiesce loop, serialised + coalesced reloads with generation ids, SourceWatcher polling *.py/metadata.txt; tests/test_devtools_reloader.py against a scripted host), devtools.bootstrap (QGIS glue the --code probe reaches), devtools.exercise (self-drive). dev --no-watch; request JSON gains watch; dev/test plans put the SDK's import locations on the QGIS PYTHONPATH. Evidence: QGIS_SDK_DEVTOOLS=1 harness 9/9 on QGIS 4.2.3: syntax error refused with revision kept, stuck worker thread refused + named + still running, reload after release, start failure after teardown disabled + recovered, 3 requests -> 1 reload, watcher reload on save answering 2001; 8 revisions. decision-15 implementation note records what differs from the proposal (no control channel, in-process poller).

Closed 2026-10-25 in PR #74 (CI green on Linux, macOS, Windows). AC1: preflight refusal keeps the revision; start failure after teardown drops partial modules, disables visibly, recovers on the next reload. AC2: serialised + coalesced reloads with generation ids, 300 ms debounce, old scope closed on unload; Vite HMR untouched. AC3: 2 s bounded quiesce, refusal names blockers, resume, explicit restart message; no thread killed.
<!-- SECTION:NOTES:END -->
