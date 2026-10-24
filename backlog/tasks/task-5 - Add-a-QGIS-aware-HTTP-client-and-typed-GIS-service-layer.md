---
id: TASK-5
title: Add a QGIS-aware HTTP client and typed GIS-service layer
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-24 16:54'
labels: []
milestone: m-2
dependencies:
  - TASK-13
  - TASK-24
priority: medium
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Resolve the proposed networking ADR into one injectable transport respecting QGIS proxy/auth/certificate settings, a generic HTTP client, and typed service clients composed over it. Keep standard WMS/WFS layer loading on QGIS providers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 UI-facing requests are non-blocking by default, with explicit timeout, cancellation, and error semantics.
- [ ] #2 A response abstraction provides status, headers, bytes/text/JSON helpers, and explicit status error handling.
- [ ] #3 Unit tests use an injected fake transport; QGIS configuration behavior has integration coverage.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: qgis-sdk agent
created: 2026-10-24 16:54
---
Moved from m-1 to m-2 on 2026-10-24 during the 0.2.0 re-scope. 0.2.0 closes on TASK-3 + TASK-28: this task blocked nothing inside m-1, sits outside the 'native runtime and Processing' surface the milestone is named for, and its networking transport still needs decision-4 resolved, which is only proposed. TASK-29 does not close until this lands, so it cannot slip silently.
---
<!-- COMMENTS:END -->
