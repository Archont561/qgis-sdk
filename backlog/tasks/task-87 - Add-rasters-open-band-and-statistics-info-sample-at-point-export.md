---
id: TASK-87
title: 'Add rasters: open, band and statistics info, sample at point, export'
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-06 15:19'
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
- [x] #1 Open, info, statistics, sample and export agree between fake and native on a fixture GeoTIFF; Layers.list returns vector and raster entries with their kinds (native tests).
- [x] #2 LayerInput(kind=raster) renders a raster-only picker natively and as a Processing parameter and is enforced on the wire; host operations regenerated and typed.
- [x] #3 doc-22 rows complete; doc-12/doc-13 document rasters; the example opens one.
<!-- AC:END -->

## Implementation notes

Implemented on the 0.10.0 sprint-4 branch, on top of the sprint-2 and sprint-3
services.

**Models.** `qgis_sdk.models.layers` gains `LayerKind`
(`vector`/`raster`), `RasterLayerInfo` (bands, per-band data types and no-data
values, extent without a CRS of its own, `(x, y)` resolution, the raster's CRS),
`RasterStatistics`, `RasterSample`, `RasterExport`, the `LayerInfo` union and the
wire schemas `RASTER_LAYER_INFO`, `RASTER_STATISTICS`, `RASTER_SAMPLE`,
`VECTOR_LAYER_INFO`. `resolution` is declared variadic and checked to be exactly
two, because a fixed-length tuple has no JSON equivalent (the declaration
contract) and a page still needs the pair. `VectorLayerInfo` gained `kind`, so
`layers.get` answers one union a page narrows with one comparison.

**Service.** `qgis_sdk.services.Rasters` - `open_raster`, `raster`,
`statistics(layer_id, band)`, `sample(layer_id, point, *, band=None)`,
`export_raster(layer_id, destination, *, overwrite=False)`. Bands are 1-based and
refused by name outside `1..band_count`; a no-data pixel or a point outside the
raster answers `None` per band, never a zero; `sample` reprojects a point whose
`crs` differs from the raster's and answers the point where it landed.

**Export policy.** `qgis_sdk.exports.plan_export` grew a `drivers` parameter, so
a raster export validates its suffix against `RASTER_EXPORT_DRIVERS` (`GTiff`,
`netCDF`) and then runs the vector export's staging, source protection and commit
unchanged. There is no second export path to keep in step.

**Fake.** `qgis_sdk.testing.FakeRasters` declares a dataset's bands, values,
holes and statistics rather than computing them, refuses to reproject (it has no
CRS database) and copies the declared file on export, so refusal, staging and
cleanup are the code the native adapter runs. `FakeLayers` now holds it and
answers both kinds from `list_layers`/`layer`; a raster id reaching a vector-only
method raises `QgisSdkUnsupportedCapabilityError`.

**Native.** `qgis_sdk.adapters.qgis.NativeRasters` reads through GDAL, names a
band's type by looking the enum up rather than assuming its spelling, translates
a missing no-data tag (NaN through QGIS) to `None`, computes statistics over
every cell rather than the provider's default sample, and writes through
`QgsRasterFileWriter` into the shared staging directory. `NativeLayers` gained
`rasters=` and answers both kinds; `NativeProject` re-opens a raster id through
`NativeRasters` so the project holds the instance the raster service owns.

**Declarations.** `LayerParameter(kind=...)` (with the `RasterInput` and
`AnyLayerInput` aliases) is one declaration with three faces: the native picker
filters by `QgsMapLayerProxyModel.Filter`, the Processing adapter builds a
`Raster Layer`, a `MapLayer` or a `Vector Layer` parameter and re-opens what the
dialog picked through the matching service, and the wire carries `layer_kind` so
a page renders the same control. A plain `LayerInput` stays vectors-only.

**Wire.** `rasters.open`, `rasters.get`, `rasters.statistics`, `rasters.sample`
under `rasters.open` and `rasters.read`; `layers.list` and `layers.get` answer
the `LayerInfo` union. `Rasters.export_raster` is deferred by name in
`DEFERRED_HOST_METHODS` (a page never supplies a filesystem destination,
decision-20), so it is a plugin action running in a `@job`.

**Tests.** `tests/services/test_rasters_contract.py` holds both backends to one
set of numbers on the checked-in `elevation.asc` (converted to a GeoTIFF for the
native run), `test_rasters_native.py` proves the four things only a real GDAL can
answer, and `tests/ui_component_contract.py` pins the three picker kinds on both
renderings.

**Documentation.** doc-22 gains the Rasters row and four operation rows;
doc-12 and doc-13 document the service; the reference example opens the bundled
raster (`open_elevation`, `sample_elevation`) and reads a band's statistics.

**Delivered on PR #167** (merge commit `785f5c1`, 2026-11-06), with TASK-88 in
one pull request because the two share the `Layers.list` change. Three
follow-ups came out of that pull request's CI rather than its first draft: the
generated client validates a union result with its named validators, the
`layers.*` queries keep the kinded union through the TypeScript stores, and the
reference example compares a grid's pixels-per-unit with `pytest.approx`,
because QGIS answers the box divided by the cell count - `0.09999999999999998`
for a 0.1 degree cell. The rules a plugin author meets are stated as six
scenarios in `tests/features/raster_reads.feature`, over `FakeRasters`.
Validation: ruff check and format clean, Python suite 2625 passed / 31 skipped /
82 native deselected, `tests/scripts` 305, the reference examples 24 pure and 8
QGIS plus `examples/server` 8 through the CI step, gherlint clean on all eight
feature files; CI run 42240353104 green (checks, Linux coverage, QGIS 3.44 LTS,
cross-platform macOS and Windows, site, backlog drift).
