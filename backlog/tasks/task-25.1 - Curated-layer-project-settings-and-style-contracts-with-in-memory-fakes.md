---
id: TASK-25.1
title: 'Curated layer, project, settings and style contracts with in-memory fakes'
status: To Do
assignee: []
created_date: '2026-10-24 14:27'
updated_date: '2026-10-24 14:27'
labels: []
milestone: m-1
dependencies: []
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
parent_task_id: TASK-25
priority: medium
type: feature
ordinal: 25100
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 1 (TASK-25). Add only the QGIS-free capabilities the accepted reference workflow needs (decision-19), as Protocols in `qgis_sdk.services`, plus in-memory fakes that satisfy the same contract tests the native adapters will.

Deliberately not a service manager: no mirror of QgsVectorLayer or QgsProject, and no capability without a caller. Every protocol added here is consumed by slice 2, 3 or 4, or by TASK-14/TASK-3.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Only capabilities the accepted reference workflow needs are added; no general PyQGIS mirror and no capability without a caller.
- [ ] #2 The new contracts and fakes import and run with qgis, PyQt and pydantic blocked, and tests/test_pure_imports.py covers every new module.
- [ ] #3 The in-memory fakes pass the same contract tests the native adapter will be held to, so fake/native parity is a test property rather than a review claim.
<!-- AC:END -->
