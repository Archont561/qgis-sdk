---
id: TASK-9
title: Define SDK and plugin release compatibility gates
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-21 21:56'
labels: []
milestone: m-4
dependencies:
  - TASK-8
  - TASK-22
  - TASK-23
references:
  - doc-8
priority: medium
type: chore
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Automate experimental 0.x SDK/bridge/plugin release gates, explicit target qualification, migration notes and package/protocol version independence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Release checks validate package metadata and build outputs on supported environments.
- [ ] #2 Supported QGIS, Python, Qt, and operating-system combinations are explicit.
- [ ] #3 The Pixi lockfile is relocked and checked against declared dependencies before CI/release relies on it.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC1 ('Release checks validate package metadata and build outputs on supported environments') needs the CI matrix, and AC3 is about CI/release relying on a checked lockfile - `pixi lock --check` passes locally (and pixi.lock is untouched by recent work), but there is no guard to record evidence in. AC2 is the one AC this window can advance, and only by writing down what is actually demonstrated (Linux with QGIS 4.1/4.2 and CPython 3.11-3.14) while listing Windows/macOS as candidates pending TASK-33 - that is a support promise, so it is your decision rather than evidence work.
---
<!-- COMMENTS:END -->
