---
id: TASK-81
title: >-
  Add the standalone app host: qgis_sdk.app.run, an optional canvas window,
  qgis-sdk run and build --target app
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-30 16:47'
labels: []
milestone: m-8
dependencies:
  - TASK-64
  - TASK-67
  - TASK-116
type: enhancement
ordinal: 81000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-52 points 1, 3, 4. qgis_sdk.app.run(PluginClass, gui=False|True, argv=) owns QgsApplication (initQgis/exitQgis), builds the context without an iface, starts the runtime; gui=True provides a main window with a QgsMapCanvas so Desktop-style bindings and the later canvas service attach to the app's window; a web view in the app uses the same bridge; ctx.host reports app; qgis-sdk run launches with the discovered QGIS environment; build --target app produces a Python distribution with a console-script launcher under the same vendoring rules; scaffold --host app.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A plugin runs headless through qgis_sdk.app.run with every non-desktop service working and ctx.host == app, and with gui=True its @toolbar/@menu bindings on actions and Dialog/Dock surfaces attach to the app window (qgis native tests, offscreen).
- [ ] #2 qgis-sdk run starts the app from a scaffolded project with the discovered QGIS environment on Linux and Windows (devtools harness; Windows row recorded or blocked per TASK-33); build --target app produces an installable distribution whose launcher runs the app, with externals probed and pure-Python packages vendored (build-install harness).
- [ ] #3 The reference example gains an app entry; doc-12 documents the app host, its lifecycle and the difference from a Desktop plugin; the bridge is unchanged and shown so.
- [ ] #4 qgis_sdk.app.run shuts down within its bounded grace deadline, names every background loop it stops and every job it abandons, and calls exitQgis exactly once, proven by pure tests over a fake backend (decision-69 points 2 and 4).

<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Bounded shutdown and loop inventory (decision-69 points 2 and 4). qgis_sdk.app.run(PluginClass, ..., grace=15.0) stops the job pump, stops the runtime, drains running jobs through jobs.quiesce() in a bounded loop, logs every job it abandons by name and settles it as cancelled, then calls exitQgis() exactly once. Every loop the host starts (job pump, dev reload watcher, the host's own timer) is named and enumerated when the runtime stops instead of being assumed stopped; ctx.host reports app.
<!-- SECTION:NOTES:END -->
