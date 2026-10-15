---
id: TASK-6
title: Implement QGIS Desktop and standalone development modes
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
labels: []
milestone: m-2
dependencies: []
priority: high
type: feature
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement qgis-sdk dev for source plugin loading in real QGIS Desktop and a clearly separate standalone PyQt/PyQGIS target. For optional WebEngine UI, run the frontend dev server/HMR and recreate/reload the plugin view on Python changes where safe, with a visible restart fallback.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Desktop mode locates QGIS from PATH or explicit configuration and loads the source plugin using a documented profile/plugin-path strategy.
- [ ] #2 Standalone mode clearly documents that it does not provide iface or plugin lifecycle.
- [ ] #3 WebEngine HMR is enabled only for projects with web UI; production builds do not use the dev server.
- [ ] #4 Unsafe or failed Python reload is reported and has a predictable restart fallback.
<!-- AC:END -->
