---
id: TASK-157
title: Place map theme authoring and layer visibility between project and styles
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/canvas.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/models/canvas.py
priority: low
type: spike
ordinal: 157000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`canvas.themes` reads the project's theme names and `canvas.apply_theme` applies one; nothing creates a theme, renames one, records which layers it shows, or turns a layer's visibility (or its scale-based visibility) on and off. The capability has no owner: it reads like project state (TASK-88), renders like cartography (TASK-93), and is reached today through the canvas - and doc-22 has no row for it anywhere.

This spike chooses the owner and the grant, and decides whether a page may change what a user sees on the map at all. It is small on purpose: the risk here is not implementation cost, it is that three future tasks each assume a different service owns it.

Proposal only: no milestone, no release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decide the owning service and the grant for theme authoring (create, rename, delete) and for layer visibility, including scale-based visibility, and state the alternative that is rejected and why.
- [ ] #2 Decide whether `canvas.apply_theme` grows companion operations (`visible_layers`, `set_visible`) or a new map-view surface carries them, keeping one vocabulary across page, console and HTTP.
- [ ] #3 Specify the fake's behaviour and one contract test set, and the native cost of a theme insert against `QgsMapThemeCollection` on a project with many layers.
- [ ] #4 State the visibility rule for a plugin that makes a layer invisible and is then unloaded, since that is user-visible state the plugin did not own.
- [ ] #5 Move the corresponding rows out of doc-22's deferred list into a proposal row, and coordinate the placement with TASK-88 and TASK-93 before either is scheduled.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read for this proposal: `services/canvas.py` (`themes()`, `apply_theme(name)` with its documented refusal for an unknown theme), `models/canvas.py` (`MapThemes` - names plus an active entry, and the note that JSON schema cannot express "active is one of names"), doc-22's rows for TASK-88/TASK-93 and its deferred list. `QgsMapThemeCollection` is not used anywhere in the tree.

The grant question is the interesting one: every existing write grant (`features.edit`, `styles.apply`) covers data or rendering, and none of them means "change what the user is looking at".
<!-- SECTION:NOTES:END -->
