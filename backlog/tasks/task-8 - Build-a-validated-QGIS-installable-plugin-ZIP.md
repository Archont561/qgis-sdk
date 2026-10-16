---
id: TASK-8
title: Build a validated QGIS-installable plugin ZIP
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-3
dependencies:
  - TASK-1
  - TASK-16
  - TASK-19
  - TASK-24
  - TASK-12
priority: high
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement qgis-sdk build with the accepted plugin-private pure-Python-first runtime policy. Validate dependencies/licenses, safe deterministic contents and two-plugin import isolation; do not install/test/publish implicitly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ZIP root has the plugin directory/layout and metadata expected by QGIS.
- [ ] #2 Archive includes required Python runtime modules and production assets while excluding tests, caches, dev tooling, and frontend dev server assets.
- [ ] #3 Build validates metadata, entry point, declared assets, and reports missing or unsupported runtime dependencies.
- [ ] #4 A clean supported QGIS profile can install and load a sample archive.
<!-- AC:END -->
