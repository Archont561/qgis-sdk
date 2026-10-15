---
id: TASK-7
title: Add layered pytest support and BDD fixtures
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
labels: []
milestone: m-2
dependencies:
  - TASK-2
priority: high
type: feature
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Provide opt-in test support for pure Python, Qt, initialized QGIS, Desktop plugin, and bridge contract layers. Integrate pytest-bdd for scenario-level behavioral cases without making every test require QGIS.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Pure Python tests run without QGIS installed/importable.
- [ ] #2 QGIS lifecycle and Qt fixtures set up and tear down deterministically and can be selected independently.
- [ ] #3 BDD scenarios can share steps/fixtures with ordinary pytest tests where appropriate.
- [ ] #4 External services and QGIS collaborators can be faked/injected in unit tests.
<!-- AC:END -->
