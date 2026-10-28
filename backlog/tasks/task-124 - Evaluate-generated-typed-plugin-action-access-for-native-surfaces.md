---
id: TASK-124
title: Evaluate generated typed plugin action access for native surfaces
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
labels: []
dependencies: []
priority: medium
type: spike
ordinal: 124000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Surface actions currently use runtime-validated ctx.actions.<id>(**inputs), but dynamic attributes do not provide reliable IDE autocomplete or static signatures. Explore generated plugin-specific Protocol or stubs; do not imply generated typing currently exists or replace runtime validation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decide a generated typing design that preserves action IDs, request/result types and valid Python names, rejects collisions, and avoids leaking one plugin action namespace into another.
- [ ] #2 Demonstrate editor/type-checker diagnostics alongside runtime validation, cross-view ownership, direct tests and deterministic stale-output detection; document fallback when generation is unavailable.
<!-- AC:END -->
