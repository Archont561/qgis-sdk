---
id: TASK-152
title: Explore map tools and layer interaction beyond geometry capture
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/canvas.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/adapters/qgis/canvas.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/declarations/_tools.py
priority: medium
type: spike
ordinal: 152000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`@tool` covers one shape of interaction: capture a point, a line or a polygon and answer with a geometry (TASK-85). Everything else a map tool does is unrepresented - identify, measure, snapping, rubber bands, custom cursors - and so is the other half of layer interaction: a context-menu entry on a layer, and the layer signals a plugin normally reacts to (visibility, CRS, features added, style changed). doc-22 records map tools as "deferred without a task"; this proposal is the task that decides.

The spike must be honest about cost: each of these is a Desktop-only, GUI-thread capability that needs a real `QgsMapCanvas` and, for some of them, a real person clicking, so qualification happens in CI on a Desktop target, never in the headless sandbox.

Proposal only: no milestone, no release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Inventory the interaction surfaces (identify, measure, snapping, rubber band, context menu, layer signals, custom cursors) against what the corpus teaches, and pick the smallest set that pays for itself - the candidates to argue first are a layer context-menu binding and a layer-change stream, because both are declaration-shaped rather than tool-shaped.
- [ ] #2 For each surface chosen, specify the declaration, the callback contract and the grant, and prove it needs no raw `iface` and no Qt object crossing the boundary.
- [ ] #3 Decide where snapping belongs: the SDK owns none today, and the honest options are "canvas configuration the SDK never touches" (a documented decision) or a `canvas.snapping` read of the current mode - state the refusal for the other.
- [ ] #4 Specify how identify reuses the features service (`features.feature` at a point) instead of returning a second feature model.
- [ ] #5 State the qualification plan per surface: what a Desktop CI leg can prove offscreen, what needs a person, and what therefore stays unqualified - no GUI claim from the Linux sandbox.
- [ ] #6 Coordinate with TASK-85 (`@tool`), TASK-96 (native catalogue) and TASK-132 (diagnostics), and close with a recommendation and its blockers.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read for this proposal: `packages/qgis-sdk-runtime/src/qgis_sdk/services/canvas.py` (capture is `capture(shape, on_capture)`, installed as a `QgsMapTool` subclass that replaces and restores the active tool), `declarations/_tools.py`, and doc-22's "Deferred without a task" row for map tools. No `QgsMapToolIdentify`, `QgsMapToolMeasure`, `QgsSnappingUtils` or `contextMenuAboutToShow` connection exists in the tree.

No Desktop QGIS in this workspace; the qualification plan in the last criterion is what the spike has to produce before any implementation is scheduled.
<!-- SECTION:NOTES:END -->
