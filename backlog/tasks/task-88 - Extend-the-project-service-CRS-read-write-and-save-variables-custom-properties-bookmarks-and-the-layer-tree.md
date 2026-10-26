---
id: TASK-88
title: >-
  Extend the project service: CRS, read, write and save, variables, custom
  properties, bookmarks and the layer tree
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-9
dependencies:
  - TASK-84
type: enhancement
ordinal: 88000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. project.crs/set_crs, read(path)/write(path)/save, variables get/set, custom properties, bookmarks list/add/zoom, layer tree as a model (groups, visibility, order, add_layer into a group, move, remove); on_changed stream; fake, native, host operations, grants.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every operation agrees between fake and native with one contract test set, the layer tree model round-trips a nested group structure, and the change stream delivers ordered frames (native tests).
- [ ] #2 Host operations regenerated and typed; destructive ones (write, remove) carry the destructive annotation the agent consent list honours.
- [ ] #3 doc-22 rows complete; doc-12/doc-13 document the service; decision-27 carries a status review for the grown host surface.
<!-- AC:END -->
