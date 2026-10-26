---
id: doc-25
title: M10 sprint train and 0.11.0 dependency order
type: guide
created_date: '2026-10-26 10:20'
---
# M10 sprint train and 0.11.0 dependency order

**Status:** Planning; starts after the TASK-90 gate. Orders work the m-10
tasks already declare; adds no scope. Sprint membership lives here and in the
milestone body ([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

## 1. Where m-10 starts from

0.10.0 leaves the kinded `LayerInfo` with vector and raster, the full
project service, canvas, features and layouts. Remaining rows of
[doc-22](doc-22%20-%20Service-coverage-map.md) for 0.11.0 ([decision-54](../../decisions/decision-54%20-%20Cover-every-QGIS-service-and-layer-kind-through-the-contract-fake-native-host-grant-pattern-under-one-grant-vocabulary.md) point 4).

## 2. Dependency read

| Task | Declared dependencies | Startable |
| --- | --- | --- |
| [TASK-91](../../tasks/task-91%20-%20Add-mesh-point-cloud-vector-tile-annotation-and-tiled-scene-layer-kinds-with-per-kind-info-models-and-open-operations.md) layer kinds | TASK-87 | after 0.10.0 |
| [TASK-93](../../tasks/task-93%20-%20Add-symbology-labelling-and-the-style-manager-renderer-and-symbol-models-labelling-settings-style-manager-read-QML-and-SLD-import-and-export.md) symbology | TASK-87 | after 0.10.0 |
| [TASK-92](../../tasks/task-92%20-%20Add-connections-and-authentication-configuration-registered-data-source-connections-browsing-opening-from-a-connection-auth-configuration-ids.md) connections + auth ids | TASK-87 | after 0.10.0 |
| [TASK-94](../../tasks/task-94%20-%20Widen-Processing-discovery-and-help-every-output-kind-model-files-and-batch-runs.md) Processing breadth | TASK-87 | after 0.10.0 |
| [TASK-95](../../tasks/task-95%20-%20Prepare-and-qualify-0.11.0-release.md) 0.11.0 gate | TASK-90, 91–94 | release gate |

## 3. Sprint train

- **Sprint 1: TASK-91.** Mesh, point cloud, vector tile, annotation,
  tiled-scene kinds with info models, open operations, pickers and
  `LayerInput(kind=)`.
- **Sprint 2: TASK-93.** Renderer, symbol and labelling models; style
  manager; QML and SLD both ways. The largest model surface; its own sprint.
- **Sprint 3: TASK-92.** Connections registry, browse, open from a
  connection, auth configuration ids - never secrets; PostGIS row recorded
  or blocked by environment.
- **Sprint 4: TASK-94.** Processing discovery and help, every output kind,
  `run_model`, `batch` as a job.
- **Gate: TASK-95.** `python-v0.11.0` paired with the next `ts-v*` minor;
  doc-22 complete or out of scope by decision for every row.

## 4. Hygiene at sprint start

- decision-16 status review with TASK-93.
- The 1.0 API-stability decision is drafted during this milestone, not
  after it: the completed doc-22 is its input.
