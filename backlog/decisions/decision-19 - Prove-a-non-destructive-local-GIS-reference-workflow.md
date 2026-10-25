---
id: decision-19
title: Prove a non destructive local GIS reference workflow
date: '2026-10-16 09:05'
status: accepted
---
## Context

The accepted vertical slice (ADR-17) needs a concrete observable workflow. The user selected local GIS rather than remote import or in-place editing in the second clarification interview on 2026-10-16.

## Decision

The reference plugin loads a vector dataset, inspects selection, runs one Processing operation, styles its output and offers equivalent native/web controls. Use a local fixture dataset; external-service availability must not gate this reference workflow. Networking gets deterministic fixtures and separately controlled integration coverage.

Preserve the source. Create a new temporary output and add it to the project through the GUI adapter only after successful completion. Clean incomplete temporary outputs on failure/cancellation. Exporting permanent results is explicit, with an explicit destination, overwrite confirmation and safe partial-file cleanup. In-place editing/transaction/undo support is not a prerequisite for this slice.

For distance-based operations require an explicit projected working CRS and units. Reject ambiguous geographic-distance input; require an explicit transformation choice where necessary rather than silently interpreting degrees as metres or selecting a projection. Define algorithm-specific unit/CRS validation in its schema/adapter; not every possible GIS operation is required to use projected coordinates.

## Consequences

- Native/web equivalence concerns behavior and validated inputs/results, not identical widget appearance.
- Real QGIS tests must prove output ownership, project addition, cancellation/failure cleanup, CRS handling and source preservation.
- Exact operation, dataset/license, transformation UI and style resources remain to be chosen and qualified.

## Evidence added (2026-10-24): the algorithm half of the reference workflow

TASK-14 implemented the "run one Processing operation, add its output to the
project after success" step of this workflow, and the tests now prove the parts of
this decision that are observable headlessly:

- **Source preserved.** A buffer run leaves the fixture dataset byte-identical
  (`sha256` before and after), and the source layer description is unchanged. No
  step writes to the input: every output is a new file under the execution's
  working directory.
- **New output, never in-place.** `Algorithms.execute` returns a *different*
  layer that the runtime owns; `invoke` adds it to the project only after the
  operation succeeded, the result matched its declared type, and cancellation was
  not requested after the operation.
- **Cleanup.** A run that fails removes its own working directory before
  re-raising, so no partial output survives; the intermediate reprojection a
  buffer needs is deleted on success as well, and only the output file remains.
- **Explicit projected working CRS and units.** `EPSG:4326` is refused as a
  working CRS ("a distance there would be degrees"), `EPSG:2227` is refused
  because its units are US survey feet, and an unknown code is refused. The
  metres interpretation is proven positively: buffers 500 m and 1500 m apart in
  distance differ in extent width by 2000 m, which cannot happen if the distance
  were applied in degrees.
- **Not every operation needs a projected CRS.** The centroid operation runs
  without any working CRS, which is the "where the operation has a distance" part
  of this decision rather than a blanket rule.

TASK-22 (0.5.0) closed the chain and the equivalence half:

- **One workflow, two front ends.** `examples/reference_plugin`'s
  `workflow.LocalGisWorkflow` chains open -> selection -> buffer (`invoke`
  without presentation) -> apply the packaged `reference/polygon-output`
  style -> add to the project, so the output is styled *before* it is
  presented. The class is the plugin's own code: the runtime ships the
  services and the reference algorithms (`qgis_sdk.reference`), never the
  chain. The plugin declares it as five actions; the native dialog `NativeForms` renders for
  `buffer` and the page's Buffer button dispatch the same bound handler, and
  the workspace harness proves both produce a styled polygon layer with the
  source's three features inside one headless QGIS with a real
  `QWebEngineView`.
- **Explicit export.** `Layers.export_vector(layer_id, destination, *,
  overwrite)` writes through `qgis_sdk.exports`: a known driver by suffix only,
  a parent that exists, no silent overwrite, a staged write renamed into place
  on success and removed on failure (`QgisSdkExportRefusedError` names every
  reason; `QgisSdkExportFailedError` leaves nothing behind). The page never
  names a path: the plugin's `export_layer` takes a *bare file name* and
  resolves it against the directory a native folder picker stored under the
  plugin's `export_directory` setting; no directory means a refusal, not a
  guess.

Still open: the transformation-choice UI (a datum transformation is taken as
QGIS's default; the reference plugin does not surface a choice). In-place
editing remains out of scope.
