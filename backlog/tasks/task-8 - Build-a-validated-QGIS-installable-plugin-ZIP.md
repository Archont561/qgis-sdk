---
id: TASK-8
title: Build a validated QGIS-installable plugin ZIP
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
labels: []
milestone: m-3
dependencies:
  - TASK-2
priority: high
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement qgis-sdk build as an end-user plugin artifact builder, distinct from installing the SDK in a developer environment. Follow the proposed policy to bundle only required SDK runtime modules in the plugin ZIP and exclude development-only files.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ZIP root has the plugin directory/layout and metadata expected by QGIS.
- [ ] #2 Archive includes required Python runtime modules and production assets while excluding tests, caches, dev tooling, and frontend dev server assets.
- [ ] #3 Build validates metadata, entry point, declared assets, and reports missing or unsupported runtime dependencies.
- [ ] #4 A clean supported QGIS profile can install and load a sample archive.
<!-- AC:END -->
