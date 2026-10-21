---
id: TASK-22
title: Complete and qualify the local GIS reference workflow
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-21 21:56'
labels: []
milestone: m-5
dependencies:
  - TASK-8
  - TASK-21
  - TASK-14
  - TASK-3
  - TASK-19
  - TASK-16
  - TASK-5
  - TASK-26
references:
  - >-
    backlog/decisions/decision-17 -
    Deliver-a-qualified-Python-first-vertical-slice-for-v1.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
  - doc-8
priority: medium
type: feature
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Complete and qualify the local GIS reference workflow. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Local fixture input, selection, Processing and styled outputs have equivalent native/web behavior and preserve source data.
- [ ] #2 Exercise new/check/test/dev/build, explicit exports and cleanup with deterministic pure and real native tests.
- [ ] #3 Record clean-profile Windows/Linux QGIS/Python/Qt/Chromium evidence and inaccessible/failing targets as blockers.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC3's clean-profile evidence has a Windows half that needs either the cross-platform job or real hardware. The Linux half is reproducible in-sandbox against headless QGIS 4.2.3 - record it as Linux-only rather than rounding it up to 'profiles'.
---
<!-- COMMENTS:END -->
