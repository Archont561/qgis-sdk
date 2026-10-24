---
id: TASK-25.5
title: Qualify the native services on a real QGIS host and record the evidence
status: To Do
assignee: []
created_date: '2026-10-24 14:28'
labels: []
milestone: m-1
dependencies:
  - TASK-25.2
  - TASK-25.3
  - TASK-25.4
references:
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
  - backlog/tasks/task-33 - Qualify-Windows-macOS-and-Desktop-QGIS-targets.md
parent_task_id: TASK-25
priority: high
type: chore
ordinal: 25500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 5 (TASK-25). The opt-in harness and the evidence record that turn slices 1-4 from "tested in the pure layer" into "qualified on a real host".

The harness belongs in packages/qgis-sdk/scripts (a wheel must not ship a tool that needs QGIS) and its QGIS-free test in packages/qgis-sdk/tests/scripts, following the existing QGIS_SDK_* opt-in pattern. The record must state what a headless host cannot prove: no GUI, canvas, 3D or Windows/macOS claim from here - TASK-33 owns those.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An opt-in harness under packages/qgis-sdk/scripts drives the native services on real QGIS 4.2.3 and is covered by a QGIS-free test in packages/qgis-sdk/tests/scripts that asserts its unavailable-host report instead of skipping silently.
- [ ] #2 The recorded evidence names exact QGIS, Python and Qt versions and lists what the headless run cannot prove, with no GUI, Windows or macOS claim.
- [ ] #3 TASK-25 notes quote the actual run; no acceptance criterion is checked on intent, and any unproven criterion stays open with its blocker named.
<!-- AC:END -->
