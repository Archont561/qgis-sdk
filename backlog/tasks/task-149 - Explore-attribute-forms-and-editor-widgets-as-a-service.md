---
id: TASK-149
title: Explore attribute forms and editor widgets as a service
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/features.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/models/features.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/ui/__init__.py
priority: medium
type: spike
ordinal: 149000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pyqgis.com spends a whole hub on attribute forms; the SDK has no surface at all (doc-31 §5.2.1). `qgis_sdk.ui`'s `Form` is an action's input window, rendered and owned by the SDK - it is not a QGIS attribute form. `services/features.py` reads and writes attribute *values*; nothing sets how a field is edited: editor-widget setup (value map, range, checkbox, date/time, relation reference), `setAlias`, default-value definitions, value constraints with their strength, or layer actions. An SDK plugin that prepares a layer for data entry therefore drops to raw PyQGIS with no lifecycle ownership, which is exactly what the contract exists to avoid.

This is a proposal, not an accepted API: it carries no milestone and promises no release. The spike decides whether form configuration is modelled (and by which service), deferred to `ctx.desktop` by an explicit decision, or offered only as a read-only projection for a generated web form.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Enumerate the form features a plugin actually needs (editor widgets per field, aliases, defaults, constraints and their strength, layer actions) against QGIS 3.44 LTS and 4.x APIs, and name the ones this SDK will not model.
- [ ] #2 Decide where the surface lives - an extension of the features service, a `fields` service of its own, or part of the project service (TASK-88) - and what a fake can answer without QGIS; state the grant and host-operation names it would need.
- [ ] #3 Specify author code with no PyQGIS import and no `QgsEditorWidgetSetup` object crossing a boundary: typed widget descriptors in the models, refused by name when this QGIS host lacks the widget type.
- [ ] #4 Decide unload and reload semantics for configuration that lives in the project or the layer rather than in the plugin, including what must not be silently reverted when a plugin is removed.
- [ ] #5 Decide whether one description can drive both the QGIS form and a generated web form, and what the page may change (authority, validation, the existing `Form` component).
- [ ] #6 Coordinate with TASK-86 (feature values), TASK-88 (project), TASK-93 (styles) and TASK-150 (schema), and close with a recorded recommendation, its blockers and no release promise.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read from the corpus side: pyqgis.com's plugin-development path has an attribute-forms and editor-widgets hub (widget setup, defaults, constraints, layer actions) with no SDK counterpart. Repo side: `packages/qgis-sdk-runtime/src/qgis_sdk/services/features.py`, `models/features.py` and `ui/` were read for this proposal; no `QgsEditorWidgetSetup`, `setFieldConstraint` or `setDefaultValueDefinition` use exists anywhere in the tree, and the board had no task for it before this one (keyword check recorded in doc-31 §8).

Nothing was executed against QGIS for this proposal. A first probe should be a headless script that sets one value map and one constraint on a GeoPackage layer, saves and re-reads the project, and reports whether the configuration survives `QgsProject.write()` - the same shape of probe recorded in TASK-128.
<!-- SECTION:NOTES:END -->
