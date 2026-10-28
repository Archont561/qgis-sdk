---
id: TASK-133
title: Explore target-aware PyQGIS type checking for plugin authors
status: To Do
assignee: []
created_date: '2026-10-28 16:24'
labels: []
dependencies: []
references:
  - 'https://github.com/leonhard-s/qgis-stubs'
priority: medium
type: spike
ordinal: 133000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explore developer-only QGIS and Qt version-aware stubs and type-checking workflows inspired by qgis-stubs; the SDK already generates typed bridge and Processing contracts. Do not ship stubs in plugin ZIPs or promise to maintain a full PyQGIS stub distribution.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Evaluate representative native-adapter and plugin code with QGIS 4 compatible stubs and a type checker in a separate development environment; record exact QGIS, Qt and stub versions, known gaps, license considerations and false positives.
- [ ] #2 Design target selection, actionable mismatch diagnostics and developer documentation consistent with the actual support matrix; keep static typing distinct from native integration evidence and QGIS 3 support.
- [ ] #3 Document a recommended approach or explicit no-go, including isolation from runtime packaging and deterministic CI; do not add an unreviewed mandatory dependency.
<!-- AC:END -->
