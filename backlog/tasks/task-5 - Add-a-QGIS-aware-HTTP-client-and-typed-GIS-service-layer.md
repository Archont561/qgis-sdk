---
id: TASK-5
title: Add a QGIS-aware HTTP client and typed GIS-service layer
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
labels: []
milestone: m-1
dependencies: []
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
