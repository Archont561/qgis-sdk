---
id: TASK-3
title: Render schema-driven native UI and dispatch Python handlers
status: To Do
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-16 12:02'
labels: []
milestone: m-1
dependencies:
  - TASK-24
  - TASK-25
priority: medium
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Use the shared plugin description for common native Qt/QGIS actions and forms while leaving behavior in normal Python methods. Preserve an escape hatch for conventional PyQt code.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A declared action and form can be rendered and dispatch validated values to a Python handler.
- [ ] #2 Signal/event binding does not serialize Python callables into the description.
- [ ] #3 Qt behavior is tested in the appropriate Qt/QGIS test layer.
<!-- AC:END -->
