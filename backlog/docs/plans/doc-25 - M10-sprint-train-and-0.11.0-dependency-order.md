---
id: doc-25
title: M10 sprint train and 0.11.0 dependency order
type: guide
created_date: '2026-10-26 10:20'
---
# M10 sprint train and 0.11.0 dependency order

**Status:** The four sprints landed (#173, #174, #175, #176; merged as
`81ba5833`, `f3c7ed67`, `e4da5a39` and `e5e24c87` on 2026-11-07) and the
TASK-95 gate is in review as #177; it records the evidence, writes the
0.11.0 and 0.8.0 migration notes and stamps the pair, and it spends no tag.
Orders work the m-10 tasks already declare; adds no scope. Sprint membership
lives here and in the milestone body
([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

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
  `LayerInput(kind=)`. Done, PR #173: the three containers the native half
  opens are built by `tests/layer_kind_fixtures.py` rather than committed.
- **Sprint 2: TASK-93.** Renderer, symbol and labelling models; style
  manager; QML and SLD both ways. The largest model surface; its own sprint.
  Done, PR #174: QML reproduces the renderer and SLD the drawing (QGIS reads
  its own SLD export back as rule-based), and `custom` is a readable graduated
  mode.
- **Sprint 3: TASK-92.** Connections registry, browse, open from a
  connection, auth configuration ids - never secrets; PostGIS row recorded
  or blocked by environment. Done, PR #175: the fixture file is built by
  `tests/connection_fixtures.py`, a registered password is proven never to
  cross a description, and the PostGIS row runs against `QGIS_SDK_TEST_POSTGIS`
  or is recorded as blocked by environment.
- **Sprint 4: TASK-94.** Processing discovery and help, every output kind,
  `run_model`, `batch` as a job. Done, PR #176: the `.model3` fixture is
  checked-in modeler output (internal version 2), `batch` is one job with a
  fraction per request and a cancellation check between them, and discovery
  and help narrowed to TASK-109 (decision-54 point 4).
- **Gate: TASK-95.** `python-v0.11.0` paired with the `ts-v0.8.0` bridge
  minor; doc-22 complete or out of scope by decision for every row. Merged
  as `0737994` (PR #177) after the gate repaired eleven inherited defects,
  and rehearsed on that commit with `python-v0.11.0-rc.1` and
  `ts-v0.8.0-rc.1`: every job green, no registry touched. The stable pair
  is uncut and waits for "publish".

## 4. Hygiene at sprint start

- decision-16 status review with TASK-93.
- The 1.0 API-stability decision is drafted during this milestone, not
  after it: the completed doc-22 is its input.
