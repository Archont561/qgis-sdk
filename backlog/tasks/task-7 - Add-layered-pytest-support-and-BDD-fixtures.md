---
id: TASK-7
title: Add layered pytest support and BDD fixtures
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-2
dependencies:
  - TASK-2
  - TASK-24
references:
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
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
- [ ] #5 Python bridge fixtures and shared contract vectors cover forged caller identity, denied operations, malformed results, cancellation acknowledgement, expired handles and non-destructive resource release without requiring QGIS for pure cases.
- [ ] #6 Behavioral/property tests cover ordered event/stream sequences, terminal/disposal races and stale-generation delivery using deterministic scheduling; separate real QWebEngine tests verify native caller binding and cleanup rather than treating fakes as integration evidence.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Extend bridge test support for proposed decision-23; TASK-4 owns the TS client/transport harness implementation. Coordinate shared fixtures without forcing Qt/QGIS or browser globals into pure Python imports. No task status or criterion is completed by this documentation update.
<!-- SECTION:NOTES:END -->
