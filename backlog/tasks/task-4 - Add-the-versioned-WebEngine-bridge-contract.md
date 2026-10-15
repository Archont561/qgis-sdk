---
id: TASK-4
title: Add the versioned WebEngine bridge contract
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
labels: []
milestone: m-1
dependencies:
  - TASK-2
priority: medium
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Expose only declared plugin operations to an optional TypeScript/QWebChannel UI through versioned request/response/error DTOs. Keep QGIS and Qt object references on the Python side.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Python and TypeScript validate the same contract fixtures.
- [ ] #2 Bridge surface is allowlisted and serializable; raw Qt/QGIS objects and arbitrary Python invocation are not exposed.
- [ ] #3 Bridge behavior can be tested without relying on live external services.
<!-- AC:END -->
