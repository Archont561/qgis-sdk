---
id: TASK-155
title: Create and own memory layers from the layers service
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/layers.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/features.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/files.py
priority: medium
type: feature
ordinal: 155000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`layers.open_vector` takes a `Path`, so every layer the SDK can reach is a file on disk. A workflow that produces an intermediate table must therefore write one, hand it to Processing, and clean it up - and the corpus's "memory layers" recipes (the standard way to build a scratch dataset in PyQGIS) have no SDK spelling at all.

This proposal adds a scratch layer the plugin can create, write through the existing editing session, read back through the features service and drop; and it states plainly what a memory layer cannot do (be saved into a project), so the refusal is by name rather than a confusing provider error.

Unmilestoned proposal: no release is promised.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The protocol carries a creation call with a geometry type and an ordered field list (name plus an SDK field type), answers with the same `VectorLayerInfo` a file layer gets, and both the fake and the native adapter (`QgsVectorLayer("...", "memory")` plus `addAttribute`) pass one contract test set.
- [ ] #2 Ownership is explicit: who removes the layer, what happens to it on unload, and a documented refusal when something asks to save a project that holds one - a memory layer cannot be persisted and must not fail silently.
- [ ] #3 The round trip is proven through the existing services: create, `begin_edit`, add features, commit, `features.page` them back, and export to a file the way `files.export` already does.
- [ ] #4 Authority is decided with host operations and a grant, doc-22 gains the row, and a page that cannot create a layer is refused by name.
- [ ] #5 doc-12 documents it and the example uses a memory layer as an algorithm's intermediate input instead of a temporary file.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read for this proposal: `services/layers.py` (`open_vector(source: Path)` builds an `ogr` layer), `services/features.py` (editing session), `models/features.py` (there is no field-type model), `services/files.py` (export). Nothing in the tree constructs a `memory:` URI and doc-22 has no row for scratch layers.

The field-type model is the hidden cost: `VectorLayerInfo` currently reports fields as names, and a memory layer must be created with types - which is also the missing half of TASK-150 and should not be designed twice.
<!-- SECTION:NOTES:END -->
