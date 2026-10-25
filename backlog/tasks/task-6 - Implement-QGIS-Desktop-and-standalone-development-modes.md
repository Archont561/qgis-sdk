---
id: TASK-6
title: Implement QGIS Desktop and standalone development modes
status: Done
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-25 13:27'
labels: []
milestone: m-3
dependencies:
  - TASK-1
  - TASK-3
  - TASK-4
  - TASK-19
  - TASK-23
priority: high
type: feature
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement real Desktop source-plugin development and an explicit reduced standalone target, with frontend HMR only for web UI. Safe Python replacement is tracked separately in the refresh task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Desktop mode locates QGIS from PATH or explicit configuration and loads the source plugin using a documented profile/plugin-path strategy.
- [x] #2 Standalone mode clearly documents that it does not provide iface or plugin lifecycle.
- [x] #3 WebEngine HMR is enabled only for projects with web UI; production builds do not use the dev server.
- [x] #4 Unsafe or failed Python reload is reported and has a predictable restart fallback.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delivered in PR #71 (sprint 2, doc-16). `qgis-sdk dev [PATH] [--mode desktop|standalone] [--qgis-prefix] [--no-web] [--port]`. Desktop locates QGIS through the shared discovery (--qgis-prefix, [tool.qgis-sdk] qgis-prefix, QGIS_PREFIX_PATH, qgis on PATH, the interpreter prefix) and starts the binary with `--profiles-path <root>/.qgis-sdk --profile dev` and the project root on QGIS_PLUGINPATH, so the source plugin loads in place with no copy or sys.path edit; documented in the scaffold README and doc-12 (AC #1). Standalone runs classFactory(None)+initGui() in a bare QgsApplication and says so in its note, README and guide: no iface, no lifecycle hooks, no reload (AC #2). A Vite dev server starts only for a project with web/ and installed dependencies, on 127.0.0.1 with a strict port; its origin reaches the QGIS process as QGIS_SDK_DEV_SERVER, which only the generated webview.py reads (page load + BrowserPolicy origin grant + bridge binding origin); builds never reference it, --no-web skips it (AC #3). Reload (toolbar action, Ctrl+Shift+R) compiles the package first and refuses a syntax error while the running revision stays up; a failed unload or start leaves the plugin disabled with the traceback on the message bar and terminal, and the fallback is to restart the command (AC #4). Source watching with automatic Python reload stays with decision-15/TASK-21. Evidence: unit tests on plans and on compiling the probe scripts, and the opt-in QGIS_SDK_DEVTOOLS=1 harness against QGIS 4.2.3: start, reload, refused revision, edited ping answering 1001 at revision 3, standalone report, Vite served page inside QGIS and HMR with the bridge still answering (doc-14).
<!-- SECTION:NOTES:END -->
