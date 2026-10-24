---
id: TASK-25.3
title: Scoped settings and notification services
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
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
parent_task_id: TASK-25
priority: low
type: feature
ordinal: 25300
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 3 (TASK-25). Scoped settings access and the native implementation of the existing `Notifications` Protocol.

Settings are read and written through the injected service only: pure code never reaches a global QSettings instance, which keeps the boundary that tests/test_pure_imports.py guards.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Settings access goes through the injected service; no core or service-contract module touches a global QSettings instance.
- [ ] #2 The native notifications adapter implements the existing Notifications Protocol without widening it, so plugin code stays runtime-agnostic.
- [ ] #3 Pure fake-based tests and one real-host check cover both services, including behaviour after the owning scope closes.
<!-- AC:END -->
