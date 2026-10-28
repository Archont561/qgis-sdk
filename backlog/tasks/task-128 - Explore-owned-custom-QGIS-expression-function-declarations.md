---
id: TASK-128
title: Explore owned custom QGIS expression function declarations
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: medium
type: spike
ordinal: 128000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The PyQGIS comparison identified no SDK equivalent for QGIS @qgsfunction. TASK-86 plans evaluating and validating expressions but does not cover user function registration. Evaluate a declaration rather than promising it is accepted; choose no release yet.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Specify typed authoring, metadata and help, safe native registration, name collisions, thread/context expectations and duplicate versions across vendored plugins; preserve access to native PyQGIS.
- [ ] #2 Specify ownership, unload/reload cleanup, registration failures and pure fake/native contract tests; decide whether or how describe and bridge permissions apply.
<!-- AC:END -->
