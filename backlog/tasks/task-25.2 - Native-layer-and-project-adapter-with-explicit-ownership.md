---
id: TASK-25.2
title: Native layer and project adapter with explicit ownership
status: To Do
assignee: []
created_date: '2026-10-24 14:28'
labels: []
milestone: m-1
dependencies:
  - TASK-25.1
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
ordinal: 25200
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 2 (TASK-25). PyQGIS-backed implementations of the layer and project contracts from slice 1: layer lifetime, selection reads, scoped resource operations and output ownership.

Ownership rules come from decision-19: the source is never mutated, a produced output is a new object, and project addition happens only after success. Every scoped operation closes through the existing `ResourceScope` rather than a new registry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Layer lifetime, selection reads and output ownership are explicit API semantics; no wrapper reproduces QgsVectorLayer and no service hides who owns an output.
- [ ] #2 Scoped resource operations close through the existing ResourceScope and are idempotent on repeat, including after a failed operation.
- [ ] #3 Fake and native adapters pass the same contract tests, and a real QGIS 4.2.3 host test proves the native path with no fake fallback.
<!-- AC:END -->
