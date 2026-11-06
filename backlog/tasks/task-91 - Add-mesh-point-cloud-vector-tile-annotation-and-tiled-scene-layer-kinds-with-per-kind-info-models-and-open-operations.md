---
id: TASK-91
title: >-
  Add mesh, point cloud, vector tile, annotation and tiled-scene layer kinds
  with per-kind info models and open operations
status: In Progress
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-06 21:40'
labels: []
milestone: m-10
dependencies:
  - TASK-87
type: enhancement
ordinal: 91000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 4. LayerInfo kinds mesh, point_cloud, vector_tile, annotation, tiled_scene with per-kind info models; open operations per kind; Layers.list, pickers and LayerInput(kind=) cover them; fake, native, host operations, grants.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each kind opens from a fixture source, lists with its info and filters in LayerInput(kind=) on the native form, in Processing and on the wire (native tests).
- [x] #2 Host operations regenerated and typed; doc-22 rows complete.
- [x] #3 doc-12/doc-13 document the kinds and which operations apply to which.
<!-- AC:END -->

## Implementation notes

Implemented as sprint 1 of the m-10 train (doc-25), on top of 0.10.0.

**Models.** `qgis_sdk.models.layers` gains `MeshLayerInfo` (`vertex_count`,
`face_count`, `group_count`), `PointCloudLayerInfo` (`point_count`,
`attribute_names`), `VectorTileLayerInfo` (`source_type`, `min_zoom`,
`max_zoom`), `AnnotationLayerInfo` (`item_count`) and `TiledSceneLayerInfo`
(`extent`); `LAYER_KIND_NAMES` grows to seven entries in wire order,
`LAYER_INFO_SCHEMAS` and `LAYER_INFO_NAMES` are the kind-to-schema and
kind-to-class maps, and `LayerInfo` is the seven-way union. `layer_kind_of` is
the one place a model is asked which kind it is.

**Services and adapters.** `Layers` gains `open_mesh`, `open_point_cloud`,
`open_vector_tile`, `open_annotation(name)` and `open_tiled_scene`; the native
adapter dispatches every kind through one `_DESCRIBERS` table, remembers the
description with the handle, and refuses a non-vector layer with a message that
names its kind. `list_layers` answers vectors first, then the kinds in the order
they were opened, then rasters.

**Processing.** The four non-vector, non-raster kinds have no
`QgsProcessingParameter*Layer` class in QGIS 3.x - only `Qgis::ProcessingSourceType`
has them - so the parameter is a generic `Map Layer` narrowed with
`setDataTypes`. A tiled scene stays unrestricted: `ProcessingSourceType.TiledScene`
is QGIS 4.0. Importing the classes that do not exist would have broken the whole
adapter, which is why this is written down here.

**Wire.** Five operations (`layers.open_mesh`, `open_point_cloud`,
`open_vector_tile`, `open_annotation`, `open_tiled_scene`), all behind the
existing `layers.open` grant; `layers.list`/`layers.get` answer `anyOf` the seven
with `kind` as the discriminator. `HOST_FINGERPRINT` moved with the surface.

**Tests.** `tests/features/layer_kinds.feature` (13 scenarios) with
`tests/layer_kind_steps.py`, `tests/test_layer_kinds.py` and
`tests/test_layer_kinds_bdd.py`; both backends answer one layer-kind contract in
`tests/services/test_layers_contract.py` over the checked-in `lagoon.2dm` (MDAL)
and a created annotation layer; `tests/host.types.ts` and `tests/stores.test.ts`
type and read the seven-way union.

**Open.** AC 1's native half holds for mesh and annotation. A vector tile, a
point cloud and a tiled scene need a binary fixture (MBTiles, LAS/COPC, a 3D
Tiles tileset) that this repository does not hold, so their native opens are
proven only through the adapter's shared dispatch, not by an opened file - see
doc-22's layer-kind row. Closing that gap is the remaining work on this AC.
