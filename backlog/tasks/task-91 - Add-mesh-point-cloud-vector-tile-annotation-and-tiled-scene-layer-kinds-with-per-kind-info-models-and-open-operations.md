---
id: TASK-91
title: >-
  Add mesh, point cloud, vector tile, annotation and tiled-scene layer kinds
  with per-kind info models and open operations
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-10
dependencies:
  - TASK-87
type: enhancement
ordinal: 91000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 4. LayerInfo kinds mesh, point_cloud, vector_tile, annotation, tiled_scene with per-kind info models; open operations per kind; Layers.list, pickers and LayerInput(kind=) cover them; fake, native, host operations, grants.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each kind opens from a fixture source, lists with its info and filters in LayerInput(kind=) on the native form, in Processing and on the wire (native tests).
- [ ] #2 Host operations regenerated and typed; doc-22 rows complete.
- [ ] #3 doc-12/doc-13 document the kinds and which operations apply to which.
<!-- AC:END -->
