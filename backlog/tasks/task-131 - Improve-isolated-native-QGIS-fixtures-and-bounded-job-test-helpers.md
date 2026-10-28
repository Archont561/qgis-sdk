---
id: TASK-131
title: Improve isolated native QGIS fixtures and bounded job test helpers
status: To Do
assignee: []
created_date: '2026-10-28 16:24'
labels: []
dependencies:
  - TASK-115
  - TASK-116
references:
  - 'https://github.com/osgeosuomi/pytest-qgis'
  - 'https://github.com/osgeosuomi/qgis_plugin_tools'
priority: medium
type: enhancement
ordinal: 131000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explore pytest-qgis and qgis-plugin-tools testing concepts for developer ergonomics while preserving SDK-owned layered tests. Extend existing qgis-sdk test rather than duplicating the completed TASK-7 foundation. Coordinate the job helper with the worker-first contract in TASK-115 and TASK-116; no dependency or release assignment is implied.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Provide opt-in native-target helpers for isolated project cleanup, Processing initialization and temporary layers, with deterministic ownership and teardown; preserve the QGIS-free pure target and distinguish standalone QGIS from the real Desktop iface.
- [ ] #2 Design a bounded job test driver with deterministic progress, success, failure and cooperative cancellation assertions, fakes for pure tests and real-worker or native coverage as appropriate; no unbounded event-loop polling or sleep-based assertions.
- [ ] #3 Test repeated tests and teardown, all-skipped native gates, pure collection without QGIS, existing Desktop lifecycle and missing host capabilities; document fixture usage and limitations.
<!-- AC:END -->
