---
id: doc-22
title: Service coverage map
type: guide
created_date: '2026-10-26 10:20'
---
# Service coverage map

**Status:** Source of truth for "what is mapped" ([decision-54](../../decisions/decision-54%20-%20Cover-every-QGIS-service-and-layer-kind-through-the-contract-fake-native-host-grant-pattern-under-one-grant-vocabulary.md) point 5). Updated
in the same change as any service work; a `tests/scripts` check that every
host operation appears here lands with [TASK-84](../../tasks/task-84%20-%20Unify-the-grant-vocabulary-across-web-agent-and-console-and-publish-the-service-coverage-map.md). An area not listed is out of
scope by decision, not by omission.

Legend — contract: Protocol in `services/`; models: plain models, no native
handle; fake: `qgis_sdk.testing`; native: `adapters/qgis/`; host: operation in
`bridge/host.py` + regenerated manifest; grant: name in the shared vocabulary.
✓ done, ◐ partial, — missing, n/a not applicable.

## Shipped (0.5.0)

| Area | Service / operations | contract | models | fake | native | host | grant | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Vector layers | `layers.open_vector`, `list`, `get`, `selection`, `export_vector` | ✓ | `VectorLayerInfo` | ✓ | ✓ | `layers.list/get/open_vector`, `files.export` | ✓ | complete (vector only) |
| Project (flat) | `project.layer_ids`, `add_layer` | ✓ | ids | ✓ | ✓ | `project.layer_ids` | ✓ | complete, narrow |
| Settings | `settings.get/set` (plugin prefix) | ✓ | str | ✓ | ✓ | `settings.get` | ✓ | complete |
| Styles | `styles.apply_style` (packaged QML) | ✓ | — | ✓ | ✓ | `styles.apply` | ✓ | complete, narrow |
| Processing | `algorithms.execute` | ✓ | `AlgorithmRequest` | ✓ | ✓ | — (actions wrap it) | n/a | execute only |
| Network | get/post/request, blocking + async, limits | ✓ | ✓ | ✓ | ✓ | `network.fetch` stream | ✓ | complete |
| Notifications | `info` | ✓ | — | ✓ | ✓ | `notifications.info` | ✓ | levels in 0.7.0 (TASK-68) |
| Workers / jobs | `offload`, `@job` | ✓ | — | ✓ | `QThreadPool` → `QgsTaskManager` (TASK-82) | n/a | n/a | complete; adapter changes in 0.9.0 |
| Desktop | `desktop.iface` (opaque) | ✓ | — | ✓ | ✓ | never | n/a | escape hatch by design |

## Planned

| Area | Service / operations | Task | Milestone | Status |
| --- | --- | --- | --- | --- |
| Canvas | `canvas.extent/scale/crs/center/zoom_to/refresh`, `themes.*`, `on_extent_changed`, `@tool` capture | [TASK-85](../../tasks/task-85%20-%20Add-the-canvas-service-extent-scale-CRS-zoom-refresh-map-themes-extent-stream-and-capture-tools.md) | 0.10.0 | planned |
| Features | `features.iterate/get`, geometry models, editing sessions | [TASK-86](../../tasks/task-86%20-%20Add-the-features-and-expressions-services-paged-iteration-filters-geometry-models-attribute-read-editing-sessions-evaluate-and-validate.md) | 0.10.0 | planned |
| Expressions | `expressions.evaluate/validate` | [TASK-86](../../tasks/task-86%20-%20Add-the-features-and-expressions-services-paged-iteration-filters-geometry-models-attribute-read-editing-sessions-evaluate-and-validate.md) | 0.10.0 | planned |
| Rasters | `rasters.open/info/statistics/sample/export`, `LayerInfo.kind` | [TASK-87](../../tasks/task-87%20-%20Add-rasters-open-band-and-statistics-info-sample-at-point-export.md) | 0.10.0 | planned |
| Project (full) | CRS, read/write/save, variables, properties, bookmarks, layer tree, `on_changed` | [TASK-88](../../tasks/task-88%20-%20Extend-the-project-service-CRS-read-write-and-save-variables-custom-properties-bookmarks-and-the-layer-tree.md) | 0.10.0 | planned |
| Layouts / atlas | `layouts.list/load_template/export`, `atlas.run` as jobs | [TASK-89](../../tasks/task-89%20-%20Add-layouts-and-atlas-list-template-load-export-to-PDF-PNG-and-SVG-as-jobs-atlas-iteration-with-progress.md) | 0.10.0 | planned |
| Layer kinds | mesh, point cloud, vector tile, annotation, tiled scene | [TASK-91](../../tasks/task-91%20-%20Add-mesh-point-cloud-vector-tile-annotation-and-tiled-scene-layer-kinds-with-per-kind-info-models-and-open-operations.md) | 0.11.0 | planned |
| Connections / auth | `connections.list/describe/browse/open_layer/test`, `auth.configurations` (ids only) | [TASK-92](../../tasks/task-92%20-%20Add-connections-and-authentication-configuration-registered-data-source-connections-browsing-opening-from-a-connection-auth-configuration-ids.md) | 0.11.0 | planned |
| Symbology | renderers, symbols, labelling, style manager, QML/SLD both ways | [TASK-93](../../tasks/task-93%20-%20Add-symbology-labelling-and-the-style-manager-renderer-and-symbol-models-labelling-settings-style-manager-read-QML-and-SLD-import-and-export.md) | 0.11.0 | planned |
| Processing breadth | `list/describe`, every output kind, `run_model`, `batch` | [TASK-94](../../tasks/task-94%20-%20Widen-Processing-discovery-and-help-every-output-kind-model-files-and-batch-runs.md) | 0.11.0 | planned |
| Grant vocabulary | `<service>.<operation>` across web, agent, console; `check --grants` | [TASK-84](../../tasks/task-84%20-%20Unify-the-grant-vocabulary-across-web-agent-and-console-and-publish-the-service-coverage-map.md) | 0.10.0 | planned |

## Out of scope by decision

| Area | Why | Where recorded |
| --- | --- | --- |
| Raw `iface`, `eval`, arbitrary Qt objects over any boundary | authority model | decisions 9, 23, 48, 49 |
| `QgsTaskManager` as a public API | jobs are the API; the manager is the adapter | decision-53 |
| Mobile (QField) | not a host | decision-52 |
| Server deployment (FCGI, containers) | operator concern | decision-52 |
| Whole-window UI tree walks | `iface` proxy by the back door | decision-51 |
