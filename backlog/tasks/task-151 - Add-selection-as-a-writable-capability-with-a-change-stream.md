---
id: TASK-151
title: Add selection as a writable capability with a change stream
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/layers.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/models/features.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/canvas.py
priority: medium
type: feature
ordinal: 151000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`layers.selection(layer_id)` returns a tuple of ids and that is the whole selection story: nothing selects, clears, or reports a change. Every "select then act" recipe in the corpus (select by expression, select by location, invert, clear) has no SDK spelling, and `ZoomTarget.selection` can only zoom to a selection somebody else made.

This proposal adds the missing half: a protocol whose operations take the three selectors the SDK already knows how to express (`ids`, an expression, an extent), a `clear`, and an `on_selection_changed` stream in the same callback-with-canceller shape as the canvas extent stream. Selection is view state, not data, so the first criterion decides the grant rather than inheriting `features.edit`.

Unmilestoned proposal: no release is promised until the authority question is answered.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One contract test set passes against the fake and the native adapter (`QgsVectorLayer.selectByIds` / `selectByExpression` / `selectByGeometry` and the `selectionChanged` signal), and an unowned layer id is refused with `QgisSdkLayerNotFoundError` as elsewhere.
- [ ] #2 Authority is decided and written down: whether selection needs a grant of its own (`features.select`) or is covered by `layers.read`, with host operations, page reach, the `check --grants` matrix and doc-22 rows landed in the same change.
- [ ] #3 The stream is ordered and coalesced, delivers the current count and ids within the page's bounds, returns a canceller, and refuses by name on a host where a selection needs a canvas the host does not have.
- [ ] #4 An expression that does not parse is refused with the expression service's own message rather than a silent empty selection; an id that is not in the layer is reported, not ignored.
- [ ] #5 doc-12 documents the service, the example uses select-then-zoom, and `zoom_to(selection)` is proven to see a selection this service made.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The existing surface was read before writing this: `packages/qgis-sdk-runtime/src/qgis_sdk/services/layers.py` (`selection` returns a tuple), `models/features.py` (`FeatureQuery` already carries ids and an expression), `services/canvas.py` (`ZoomTarget.selection` with a documented refusal when nothing is selected). There is no `select` operation among the 34 host operations of `qgis_sdk.bridge.host`, and no board task.

A prototype should start from `QgsVectorLayer.selectByExpression` on the fixture layer the 0.10.0 feature tests already use, with a fake that stores a declared selection so the contract tests can compare.
<!-- SECTION:NOTES:END -->
