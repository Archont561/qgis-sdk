---
id: TASK-25.4
title: Apply packaged QML to compatible outputs
status: To Do
assignee: []
created_date: '2026-10-24 14:28'
labels: []
milestone: m-1
dependencies:
  - TASK-25.2
references:
  - >-
    backlog/decisions/decision-16 -
    Separate-reusable-layer-styles-from-UI-themes.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
parent_task_id: TASK-25
priority: medium
type: feature
ordinal: 25400
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 4 (TASK-25). Apply a reviewed packaged QML style resource to a compatible output through the layer service, and refuse incompatible targets explicitly.

Scope boundary from decision-16: this is layer styling, not UI theming. No global stylesheet or palette mutation, and no promise of CSS/QSS equivalence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reviewed packaged QML resource applies to a compatible output through the layer service, with the style resource shipped with the package rather than read from an ambient path.
- [ ] #2 A layer/geometry/field mismatch is refused with a structured QgisSdk error naming the incompatibility, never a partial or silent application.
- [ ] #3 No global stylesheet or application palette is mutated, and native theme inheritance is untouched, proven by a test rather than by review.
<!-- AC:END -->
