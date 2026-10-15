---
id: TASK-9
title: Define SDK and plugin release compatibility gates
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
labels: []
milestone: m-3
dependencies:
  - TASK-8
priority: medium
type: chore
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Document and automate the release matrix for the developer SDK, bridge package, and built plugin artifact. Resolve supported QGIS/Python/platform claims and lockfile consistency before releases.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Release checks validate package metadata and build outputs on supported environments.
- [ ] #2 Supported QGIS, Python, Qt, and operating-system combinations are explicit.
- [ ] #3 The Pixi lockfile is relocked and checked against declared dependencies before CI/release relies on it.
<!-- AC:END -->
