---
id: TASK-150
title: Explore field and schema management on the features service
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/features.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/layers.py
priority: medium
type: spike
ordinal: 150000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The editing service writes features; it cannot touch the schema (doc-31 §5.2.2). There is no way to add, rename, delete or reorder a field, change its type, compute one with the field calculator, or join attributes - so an SDK plugin cannot prepare the layer it is about to write to, which is the first half of most data-preparation workflows the corpus teaches.

Some of the gap is already closable through `algorithms.run` (native `joinattributesbylocation`), so the spike must first separate what is genuinely missing from what a composition of the expression and editing services could do.

This is a proposal, not an accepted API: no milestone, no release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 List the schema operations the SDK should own and the ones it should keep refusing, and for each of them state which providers (`ogr` GeoPackage, PostGIS, memory) support it at all - a memory layer can always accept a field, a WFS layer never can.
- [ ] #2 Decide whether the field calculator is an operation of its own or a documented composition of `expressions.evaluate` and the editing session, with the cost of large layers stated.
- [ ] #3 Specify destructive-change safety: what an SDK-authored field removal requires before it runs, how it is reported, and why an undoable edit session is or is not the right vehicle for a schema change.
- [ ] #4 Decide the ownership model - does a field the plugin added stay when the plugin is unloaded - and the corresponding refusal language, in the same vocabulary as the rest of the services.
- [ ] #5 Define the fake's behaviour (declare-supported operations per layer) and the contract tests that prove fake and native answer alike.
- [ ] #6 Coordinate with TASK-86 (editing), TASK-92 (connections, where schema edits are the risky case) and TASK-94 (Processing), and close with a recommendation and its blockers.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Grounded in `services/features.py` (page, feature, `begin_edit` and the `EditingSession` add/update/delete/commit/rollback methods) - no operation reads or writes a field definition, and `backlog/docs/plans/doc-22` has no row for it. `QgsVectorLayer.addAttribute`/`deleteAttribute` do not appear anywhere in the tree.

No QGIS was available for this proposal. The first probe should decide the provider-support matrix by trying one add-attribute and one delete-attribute on a GeoPackage, a memory layer and (if reachable) PostGIS, and recording the refusal messages verbatim.
<!-- SECTION:NOTES:END -->
