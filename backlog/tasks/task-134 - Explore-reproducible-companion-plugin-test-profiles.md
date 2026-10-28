---
id: TASK-134
title: Explore reproducible companion-plugin test profiles
status: To Do
assignee: []
created_date: '2026-10-28 16:24'
labels: []
dependencies: []
references:
  - 'https://github.com/3liz/qgis-plugin-manager'
priority: low
type: spike
ordinal: 134000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explore pinned companion QGIS plugins in throwaway integration-test profiles, inspired by qgis-plugin-manager, for plugin coexistence and future cross-plugin action tests. This concerns developer test fixtures, not Python package installation in end-user QGIS.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Design explicit opt-in source, version and integrity pinning, stable versus experimental selection, cache and offline behavior; test using local recorded repository fixtures without mandatory network access.
- [ ] #2 Keep profiles isolated from user installations and safely validate archives, paths and source trust; document that third-party plugin code executes with QGIS privileges and is not sandboxed.
- [ ] #3 Assess integration with existing dev and Desktop test staging and TASK-125; record a go/no-go with native qualification requirements and no implicit release assignment.
<!-- AC:END -->
