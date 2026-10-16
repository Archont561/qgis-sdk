---
id: TASK-9
title: Define SDK and plugin release compatibility gates
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-5
dependencies:
  - TASK-8
  - TASK-22
  - TASK-23
priority: medium
type: chore
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Automate experimental 0.x SDK/bridge/plugin release gates, explicit target qualification, migration notes and package/protocol version independence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Release checks validate package metadata and build outputs on supported environments.
- [ ] #2 Supported QGIS, Python, Qt, and operating-system combinations are explicit.
- [ ] #3 The Pixi lockfile is relocked and checked against declared dependencies before CI/release relies on it.
<!-- AC:END -->
