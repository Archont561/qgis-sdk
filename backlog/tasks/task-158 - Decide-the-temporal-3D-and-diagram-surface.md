---
id: TASK-158
title: Decide the temporal, 3D and diagram surface
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/canvas.py
  - backlog/tasks/task-93 - Add-symbology-labelling-and-the-style-manager-renderer-and-symbol-models-labelling-settings-style-manager-read-QML-and-SLD-import-and-export.md
priority: low
type: spike
ordinal: 158000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three cartography areas have no SDK surface and no owner: temporal control (filter a layer by time, animate, expose the range), 3D map views (settings, an offscreen 3D view, extrusion), and diagrams (a diagram renderer beside the symbol renderer). doc-22 records 3D as "deferred without a task" and says nothing about the other two, so each session rediscovers them from the corpus and moves on.

This spike answers all three at once, separately and honestly, including the one answer that is usually right for 3D: decline it, in writing, with the reason (no GPU in the qualification environment; `ctx.desktop` remains the escape hatch). Declining is a valid outcome only if it is recorded as a decision, not as silence.

Proposal only: no milestone, no release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Separate what a plugin actually needs in each area - a time filter versus an animation, a 3D view versus a 3D export, a diagram configuration versus a rendered image - and cost each against the existing services.
- [ ] #2 State the qualification reality: what a headless Linux job can prove (temporal filtering, time ranges; a rendered 3D snapshot is unproven), what needs a real Desktop, and what needs a GPU and therefore stays out of CI.
- [ ] #3 Decide the owner for each: styles (TASK-93) for diagrams, a canvas extension for temporal, nothing for 3D - or name the new service and its grant if any of them is accepted.
- [ ] #4 Decide each of the three separately with an explicit accept or decline, and record a decision for every decline so the board stops reopening it.
- [ ] #5 Update doc-22's deferred and out-of-scope tables to match, and link the decision from doc-31 §5.2 so the review and the board agree.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read for this proposal: `services/canvas.py` and `models/canvas.py` (extent, scale, CRS, centre, themes, capture - no temporal, no 3D), doc-22's deferred row for 3D map views, and `backlog/tasks/task-93` (symbology and labelling; diagrams are not named in it). `QgsTemporalController`, `Qgs3DMapSettings` and `QgsDiagramRenderer` appear nowhere in the tree.

No 3D or GUI QGIS in this workspace, so criterion 2 is the part this task must not bluff: the repo's standing rule is that no GUI, canvas or 3D claim may originate from the headless sandbox.
<!-- SECTION:NOTES:END -->
