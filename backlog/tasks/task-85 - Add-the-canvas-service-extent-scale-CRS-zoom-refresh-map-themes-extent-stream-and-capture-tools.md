---
id: TASK-85
title: >-
  Add the canvas service: extent, scale, CRS, zoom, refresh, map themes, extent
  stream and capture tools
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-9
dependencies:
  - TASK-84
  - TASK-81
type: enhancement
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. Protocol, models, fake, native (QgsMapCanvas on Desktop and in the app window; refuses by name on the server), host operations and grants: canvas.extent/scale/crs/center, zoom_to(layer|selection|extent), refresh, themes.list/apply, on_extent_changed stream; @tool declaration for point/line/polygon capture returning geometry models; bridge manifest regenerated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every operation works against the fake and the native canvas with one contract test set, the extent stream delivers ordered frames, and a capture tool returns the drawn geometry (qgis native tests, offscreen).
- [ ] #2 The page reaches canvas.* through qgis.host under a grant, typed in generated/host.ts; HOST_FINGERPRINT moved and the fixtures were regenerated, never hand-edited; the console and agent see the same operations.
- [ ] #3 doc-22 row complete; doc-12/doc-13 document the service; the example uses zoom_to after an algorithm.
<!-- AC:END -->
