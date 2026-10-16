---
id: TASK-6
title: Implement QGIS Desktop and standalone development modes
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-16 12:02'
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
- [ ] #1 Desktop mode locates QGIS from PATH or explicit configuration and loads the source plugin using a documented profile/plugin-path strategy.
- [ ] #2 Standalone mode clearly documents that it does not provide iface or plugin lifecycle.
- [ ] #3 WebEngine HMR is enabled only for projects with web UI; production builds do not use the dev server.
- [ ] #4 Unsafe or failed Python reload is reported and has a predictable restart fallback.
<!-- AC:END -->
