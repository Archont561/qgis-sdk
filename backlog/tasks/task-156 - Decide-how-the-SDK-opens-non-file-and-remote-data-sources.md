---
id: TASK-156
title: Decide how the SDK opens non-file and remote data sources
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/services/layers.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/adapters/qgis/layers.py
  - backlog/tasks/task-91 - Add-mesh-point-cloud-vector-tile-annotation-and-tiled-scene-layer-kinds-with-per-kind-info-models-and-open-operations.md
  - backlog/tasks/task-92 - Add-connections-and-authentication-configuration-registered-data-source-connections-browsing-opening-from-a-connection-auth-configuration-ids.md
priority: high
type: spike
ordinal: 156000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`layers.open_vector(source: Path)` builds `QgsVectorLayer(path, ..., "ogr")`, so the SDK can open a local file and nothing else (doc-31 §5.2.8). A PostGIS table, a WFS layer, a WMS or XYZ raster, a vector tile set, an OGC API collection or a virtual layer cannot be expressed at all - the signature has no provider name and no datasource parameters - and that is a large part of what the corpus teaches under "spatial data" and "web services".

TASK-91 adds layer *kinds* and TASK-92 adds *connections*, but neither widens the open surface, so this gap would survive both. This spike decides the shape: a typed layer source (provider plus parameters, built from a connection id or a URI), whether `Path` remains sugar, and what a pure fake can honestly promise about a source it cannot reach.

Proposal only, and an invasive one: the signature change touches a shipped service, so it needs the version policy question answered before it is scheduled.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Map the sources to be supported (PostGIS, WFS/WMS/WCS, XYZ, vector tiles, OGC API - Features, GeoPackage sublayers, virtual layers) onto QGIS's provider name plus datasource parameters, and say for each whether opening also needs a connection (TASK-92) or a plugin-owned provider.
- [ ] #2 Decide the signature: a typed source value object versus an overloaded string, whether `open_vector(Path)` stays as sugar, and - if the signature changes - which release may take the break under the version policy.
- [ ] #3 Specify honest failure: a provider this QGIS build lacks, a bad URI, an unreachable endpoint and an authentication requirement are four different answers, refused by name, never a silent `ogr` fallback.
- [ ] #4 Decide what the fake does with a source it cannot reach (accept a declared source only), and prove the contract tests stay QGIS-free and offline - no test may hit the network.
- [ ] #5 Assign row ownership against TASK-91 and TASK-92 in doc-22 so one capability is not modelled twice, and record which of the three tasks delivers which part.
- [ ] #6 Record the recommendation, its blockers, and the interaction with TASK-87 (rasters) and TASK-93 (styles, where a remote layer's style may not be settable).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read for this proposal: `packages/qgis-sdk-runtime/src/qgis_sdk/services/layers.py` (one `ogr` path), `adapters/qgis/layers.py`, `models/features.py` (no source model), doc-22's rows for TASK-91/92 and its "Out of scope by decision" table. `QgsProviderRegistry`, `QgsDataSourceUri` and any `type=xyz`/`url=` provider string are absent from the packages.

The corpus pressure is real: pyqgis.com's PostGIS, WMS/WFS and OGC-API guides all start from a datasource URI, and its "load a layer from a database" recipes have no path through this SDK at all.
<!-- SECTION:NOTES:END -->
