---
id: TASK-87
title: 'Add rasters: open, band and statistics info, sample at point, export'
status: To Do
assignee: []
created_date: '2026-10-26T10:11:00Z'
labels: []
milestone: m-9
dependencies:
  - TASK-84
type: enhancement
ordinal: 87000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. LayerInfo gains kind with a RasterLayerInfo (bands, data types, no-data, extent, resolution, CRS); rasters.open(source), info, statistics(band), sample(point, crs), export(FileRef) as a job; Layers.list returns every kind with its info; fake, native, host operations, grants; the native form and Processing mapping gain a raster LayerInput kind filter.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Open, info, statistics, sample and export agree between fake and native on a fixture GeoTIFF; Layers.list returns vector and raster entries with their kinds (native tests).
- [ ] #2 LayerInput(kind=raster) renders a raster-only picker natively and as a Processing parameter and is enforced on the wire; host operations regenerated and typed.
- [ ] #3 doc-22 rows complete; doc-12/doc-13 document rasters; the example opens one.
<!-- AC:END -->
