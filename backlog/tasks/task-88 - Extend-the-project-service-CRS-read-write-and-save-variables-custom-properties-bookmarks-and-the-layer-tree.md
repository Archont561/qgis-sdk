---
id: TASK-88
title: >-
  Extend the project service: CRS, read, write and save, variables, custom
  properties, bookmarks and the layer tree
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-06 15:19'
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
- [x] #1 Every operation agrees between fake and native with one contract test set, the layer tree model round-trips a nested group structure, and the change stream delivers ordered frames (native tests).
- [x] #2 Host operations regenerated and typed; destructive ones (write, remove) carry the destructive annotation the agent consent list honours.
- [x] #3 doc-22 rows complete; doc-12/doc-13 document the service; decision-27 carries a status review for the grown host surface.
<!-- AC:END -->

## Implementation notes

Implemented on the 0.10.0 sprint-4 branch, on top of the sprint-2 services.

**Models.** `qgis_sdk.models.project` holds the QGIS-free value types: `LayerNode`
(id, name, `kind` of `layer`/`group`, own visibility, parent group id),
`LayerTree` (a flat pre-order list with `node`/`children_of`/`layer_ids`/
`group_ids`), `ProjectEntry`, `Bookmark`, `ProjectFile`, `ProjectChange` (one of
the six declared kinds) and their wire schemas.

**Service.** `qgis_sdk.services.Project` grew from two methods to twenty-one:
`layer_tree`, `move_layer`, `set_visible`, `crs`/`set_crs`, `variables`/
`set_variable`/`unset_variable`, `custom_properties`/`set_custom_property`/
`unset_custom_property`, `bookmarks`/`bookmark`/`add_bookmark`/
`remove_bookmark`, `read`/`write`/`save` and `watch_changes`. Every mutation
answers the tree or the list it produced, so a caller never re-reads to find out
what its own call did.

**Fake.** `qgis_sdk.testing.FakeProject` keeps one in-memory project and writes a
small, documented JSON document (`format: qgis-sdk-fake-project`), so a pure test
round-trips a project without QGIS; `set_tree` declares a nested structure
outright, because building a tree is setup rather than a service call.

**Native.** `qgis_sdk.adapters.qgis.NativeProject` edits
`QgsProject.instance()`: the tree through `layerTreeRoot`, the CRS through
`setCrs`, the entries through `customVariables`/`customProperty`, bookmarks
through the bookmark manager, and the file through `read`/`write` with a staged
partial file. A group has no id in QGIS, so the adapter derives one from the
group's name path (`group:Elevation/Detail`) - stable while a group keeps its
name and its parent's, and the documented limit is that two sibling groups with
one name are as ambiguous here as they are to `findGroup`. The change stream
delivers the service's own frames once and passes QGIS's signals through for
changes the service did not make, so a frame is a change and not its echo.

**Wire.** Twenty-two operations - twenty-one calls and the `project.changed`
stream - under `project.read` and `project.write`. `HostOperation` gained the
`destructive` field the manifest carries and the agent consent list reads:
`project.read`, `project.write`, `project.save`, `project.remove_layer`,
`project.remove_bookmark`, `project.unset_variable` and
`project.unset_property` carry it, and `tests/test_bridge_host_project.py` pins
the list, so an operation cannot become destructive by accident. `HOST_FINGERPRINT`
moved once for the two services and the generated client was regenerated.

**Tests.** `tests/services/test_project_contract.py` asserts the tree as a tree
(`children_of` over a nested group structure), the CRS, both entry stores, the
bookmarks, a write/read/save round-trip, the refuse-overwrite rule, an ordered
change stream and a cancelled subscription, against both backends;
`tests/test_bridge_host_project.py` holds the wire to the models and to the
annotation.

**Documentation.** doc-22 gains the Project (full) row and twenty-two operation
rows plus the annotation note; doc-12 and doc-13 document the service;
decision-27 carries the status review for the grown surface (59 operations, 19
grants, 7 destructive, 10 deferred).

**Delivered on PR #167** (merge commit `785f5c1`, 2026-11-06), with TASK-87. The
native adapter needed three QGIS-version spellings before it was green - a
`readEntry` that answers `(value, found)`, a bookmark manager that takes either
a `QgsReferencedRectangle` or a `QgsBookmark`, and project-level signals rather
than a registry-bridge guess - and each is written as the dual form with a shape
or `TypeError` guard instead of one build's spelling. The rules are stated as
eight scenarios in `tests/features/project_service.feature`. Validation: ruff
check and format clean, Python suite 2625 passed / 31 skipped / 82 native
deselected, `tests/scripts` 305, the reference examples 24 pure and 8 QGIS plus
`examples/server` 8 through the CI step, gherlint clean on all eight feature
files; CI run 42240353104 green (checks, Linux coverage, QGIS 3.44 LTS,
cross-platform macOS and Windows, site, backlog drift).
