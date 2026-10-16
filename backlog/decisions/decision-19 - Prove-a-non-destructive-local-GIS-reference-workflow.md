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
