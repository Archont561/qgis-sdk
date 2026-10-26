---
id: TASK-93
title: >-
  Add symbology, labelling and the style manager: renderer and symbol models,
  labelling settings, style manager read, QML and SLD import and export
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-10
dependencies:
  - TASK-87
type: enhancement
ordinal: 93000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 4; extends decision-16. symbology.get/set renderer for single, categorized, graduated and rule-based renderers with symbol models for the common layers, labelling get/set, style_manager list, apply_style from QML or SLD text and export to both; fake, native, host operations, grants.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Renderer, symbol and labelling models round-trip through set/get on native layers for every supported renderer; QML and SLD export then import reproduce the renderer (native tests).
- [ ] #2 Host operations regenerated and typed; destructive annotations on set operations.
- [ ] #3 doc-22 rows complete; decision-16 reviewed; doc-12/doc-13 document symbology.
<!-- AC:END -->
