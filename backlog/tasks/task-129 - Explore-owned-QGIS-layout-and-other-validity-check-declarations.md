---
id: TASK-129
title: Explore owned QGIS layout and other validity check declarations
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: medium
type: spike
ordinal: 129000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The 2019 PyQGIS talk shows @check.register for layout validity checks. No equivalent SDK declaration or dedicated backlog task was found; TASK-89 covers layout/atlas export, not registration. This is a proposal, not an accepted API.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Assess supported QGIS 4 validity check kinds and define severity, title, details, context, localization and data-safety requirements; separate QGIS validity checks from qgis-sdk source lint.
- [ ] #2 Design scoped registration, collision behavior, unload/reload cleanup, safe errors and no-QGIS fakes, and qualify against a native QGIS layout; determine interaction with TASK-89 without promising a release.
<!-- AC:END -->
