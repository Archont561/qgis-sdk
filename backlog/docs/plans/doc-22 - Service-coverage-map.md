---
id: doc-22
title: Service coverage map
type: guide
created_date: '2026-10-26 10:20'
---
# Service coverage map

**Status:** Source of truth for "what is mapped" ([decision-54](../../decisions/decision-54%20-%20Cover-every-QGIS-service-and-layer-kind-through-the-contract-fake-native-host-grant-pattern-under-one-grant-vocabulary.md) point 5). Updated
in the same change as any service work; the `tests/scripts` check that every
host operation appears here landed with [TASK-84](../../tasks/task-84%20-%20Unify-the-grant-vocabulary-across-web-agent-and-console-and-publish-the-service-coverage-map.md)
(`test_service_coverage.py`), and the exhaustive list is [Host operations](#host-operations). An area not listed is out of
scope by decision, not by omission; explicitly marked proposals below still
require a decision before being added to the committed service scope.

**Safety warning:** the existing vector export and generic Processing entries
below have known data-safety gaps: [TASK-118](../../tasks/task-118%20-%20Prevent-layer-exports-from-replacing-their-source-dataset.md)
and [TASK-119](../../tasks/task-119%20-%20Enforce-honest-Processing-output-safety-for-explicit-destinations.md).
Their presence in the matrix records implemented components, not proof that
their documented non-destructive guarantees hold in every case.

Legend — contract: Protocol in `services/`; models: plain models, no native
handle; fake: `qgis_sdk.testing`; native: `adapters/qgis/`; host: operation in
`bridge/host.py` + regenerated manifest; grant: name in the shared vocabulary.
✓ done, ◐ partial, — missing, n/a not applicable.

## Shipped

The minor an area landed in is in the Area column: (0.5.0) through (0.10.0),
newest last.

| Area | Service / operations | contract | models | fake | native | host | grant | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Vector layers | `layers.open_vector`, `list`, `get`, `selection`, `export_vector` | ✓ | `VectorLayerInfo` | ✓ | ✓ | `layers.list/get/open_vector`, `files.export` | ✓ | complete (vector only) |
| Project (flat) | `project.layer_ids`, `add_layer` | ✓ | ids | ✓ | ✓ | `project.layer_ids` | ✓ | complete, narrow |
| Settings | `settings.get/set` (plugin prefix) | ✓ | str | ✓ | ✓ | `settings.get` | ✓ | complete |
| Styles | `styles.apply_style` (packaged QML) | ✓ | — | ✓ | ✓ | `styles.apply` | ✓ | complete, narrow |
| Processing (plugin-local) | `algorithms.execute` | ✓ | `AlgorithmRequest` | ✓ | ✓ | — (actions wrap it) | n/a | complete |
| Processing (any provider, 0.7.0) | `algorithms.providers/list/describe/run`, generated `qgis_sdk.processing.*` | ✓ | `AlgorithmInfo`, `AlgorithmRun`, `RunResult` | ✓ (snapshot + `script_run`) | ✓ | `algorithms.providers/list/describe/run` | `algorithms.read`, `algorithms.run` | complete ([TASK-109](../../tasks/task-109%20-%20Generate-the-Processing-catalogue-typed-registry-in-Python-and-TypeScript-list-describe-and-run-for-any-provider.md), decision-64); models and batch in TASK-94 |
| Features (0.10.0) | `features.page`, `features.feature`, paging/filters, geometry encodings | ✓ | `Feature`, `FeaturePage`, `FeatureQuery`, `Geometry` | ✓ (`FakeFeatures`, declared encodings, no conversion) | ✓ (`QgsFeatureRequest`, `$id > cursor`) | `features.page` stream, `features.get` | `features.read` | complete ([TASK-86](../../tasks/task-86%20-%20Add-the-features-and-expressions-services-paged-iteration-filters-geometry-models-attribute-read-editing-sessions-evaluate-and-validate.md)); 100 features a page by default, 1000 at most, an over-size ask refused by name |
| Expressions (0.10.0) | `expressions.evaluate`, `expressions.validate` | ✓ | `ExpressionOutcome`, `ExpressionCheck` | ✓ (documented subset; functions refused by name) | ✓ (`QgsExpression` in a prepared context) | `expressions.evaluate`, `expressions.validate` | `expressions.evaluate` | complete ([TASK-86](../../tasks/task-86%20-%20Add-the-features-and-expressions-services-paged-iteration-filters-geometry-models-attribute-read-editing-sessions-evaluate-and-validate.md)); "valid, value null" and "invalid, message" are different answers |
| Editing (0.10.0) | `Features.begin_edit`, `EditingSession.add/update/delete/commit/rollback` | ✓ | `EditOutcome` | ✓ (declares `atomic=True/False`) | ✓ (the layer's edit buffer) | `editing.begin/add/update/delete/commit/rollback` | `features.edit` | complete ([TASK-86](../../tasks/task-86%20-%20Add-the-features-and-expressions-services-paged-iteration-filters-geometry-models-attribute-read-editing-sessions-evaluate-and-validate.md)); session lifetime is the view, no cross-provider atomicity promised |
| Rasters (0.10.0) | `rasters.open/raster/statistics/sample`, `LayerInfo.kind` | ✓ | `RasterLayerInfo`, `RasterStatistics`, `RasterSample` | ✓ (`FakeRasters`, declared values and holes) | ✓ (GDAL through `QgsRasterLayer`) | `rasters.open/get/statistics/sample` | `rasters.open`, `rasters.read` | complete ([TASK-87](../../tasks/task-87%20-%20Add-rasters-open-band-and-statistics-info-sample-at-point-export.md)); a raster export is `files.export` over a raster-owned destination — no raster writer of its own |
| Layouts and atlases (0.10.0) | `layouts.list`, `load_template`, `export`, `render`, `run_atlas`, `render_atlas` | ✓ | `LayoutInfo`, `LayoutExport`, `AtlasPage`, `AtlasExport`, `LayoutSettings` | ✓ (`FakeLayouts`, marker files, declared coverage ids) | ✓ (`QgsLayoutManager`, `QgsLayoutExporter`, offscreen) | `layouts.list`, `layouts.load_template`, `layouts.export`, `layouts.atlas` | `layouts.read`, `layouts.write`, `layouts.export` | complete ([TASK-89](../../tasks/task-89%20-%20Add-layouts-and-atlas-list-template-load-export-to-PDF-PNG-and-SVG-as-jobs-atlas-iteration-with-progress.md)); export and atlas are jobs with a bar and a cancel button, the wire forms are one request that ends with a ref, and the two render operations carry the destructive annotation because an export replaces the file a page's own write ref names |
| Project, full (0.10.0) | `project.crs/set_crs`, `read/write/save`, variables, custom properties, bookmarks, `layer_tree`/`add_layer`/`remove_layer`/`move_layer`/`set_visible`, `watch_changes` | ✓ | `LayerTreeNode`, `Bookmark`, `ProjectEntry`, `WriteOutcome` | ✓ (private JSON format) | ✓ (`.qgs` through `QgsProject`) | `project.*` — see the table below | `project.read`, `project.write` | complete ([TASK-88](../../tasks/task-88%20-%20Extend-the-project-service-CRS-read-write-and-save-variables-custom-properties-bookmarks-and-the-layer-tree.md)); the layer tree is a model, never a `QgsLayerTreeGroup` handle |
| Network | get/post/request, blocking + async, limits | ✓ | ✓ | ✓ | ✓ | `network.fetch` stream | ✓ | complete |
| Blobs (decision-59) | `HostAuthority.mint_blob`/`inline_or_blob`/`read_blob` | ✓ | `BlobRef`, `BlobChunk` | ✓ (authority over fakes) | ✓ (same code: the authority holds no Qt) | `blob.get` | `blob.read` | complete; the 256 KiB inline cap and the chunk size are measured in a real `QWebEngineView` by the native suite |
| Notifications | `info` | ✓ | — | ✓ | ✓ | `notifications.info` | ✓ | levels in 0.7.0 (TASK-68) |
| Workers / jobs | `offload`, `@job` | ✓ | — | ✓ | `QThreadPool` → `QgsTaskManager` (TASK-82) | n/a | n/a | existing step model; worker-first named jobs and lint planned for 0.9.0 (TASK-115–117; decision-65) |
| Desktop | `desktop.iface` (opaque) | ✓ | — | ✓ | ✓ | never | n/a | escape hatch by design |

## Host operations

Every operation the host answers, as of the 0.11.0 development line: the 0.10.0
surface plus the layer kinds of [TASK-91](../../tasks/task-91%20-%20Add-mesh-point-cloud-vector-tile-annotation-and-tiled-scene-layer-kinds-with-per-kind-info-models-and-open-operations.md)
and the symbology of [TASK-93](../../tasks/task-93%20-%20Add-symbology-labelling-and-the-style-manager-renderer-and-symbol-models-labelling-settings-style-manager-read-QML-and-SLD-import-and-export.md)
([decision-54](../../decisions/decision-54%20-%20Cover-every-QGIS-service-and-layer-kind-through-the-contract-fake-native-host-grant-pattern-under-one-grant-vocabulary.md)
point 5). The five `layers.open_*` rows of the other kinds reuse `layers.open`,
so the grant vocabulary does not grow with a kind: a project grants "open a
layer", not "open a mesh". The id is `<service>.<operation>`; the grant is the name that selects it
in `[tool.qgis-sdk.web] grants` and `[tool.qgis-sdk.console] grants`, and `wraps`
is the Protocol method the operation answers, so a reader can follow a name to
the code.

The page and the console reach these through the same vocabulary and differ only
in their default: a page reaches what its `grants` name, while the console
reaches every operation unless `[tool.qgis-sdk.console] grants` narrows it. The
plugin HTTP allowlist (`PluginHttpServer(actions=...)`) is authority too, and it
names **plugin actions and streams**, not host operations, so it has no row here.

| Operation | Grant | Area | Wraps |
| --- | --- | --- | --- |
| `layers.list` | `layers.read` | Layers (vector and raster) | `Layers.list_layers` |
| `layers.get` | `layers.read` | Layers | `Layers.layer` |
| `layers.open_vector` | `layers.open` | Layers (vector) | `Layers.open_vector` |
| `layers.open_mesh` | `layers.open` | Layers (mesh) | `Layers.open_mesh` |
| `layers.open_point_cloud` | `layers.open` | Layers (point cloud) | `Layers.open_point_cloud` |
| `layers.open_vector_tile` | `layers.open` | Layers (vector tile) | `Layers.open_vector_tile` |
| `layers.open_annotation` | `layers.open` | Layers (annotation) | `Layers.open_annotation` |
| `layers.open_tiled_scene` | `layers.open` | Layers (tiled scene) | `Layers.open_tiled_scene` |
| `rasters.open` | `rasters.open` | Rasters | `Rasters.open_raster` |
| `rasters.get` | `rasters.read` | Rasters | `Rasters.raster` |
| `rasters.statistics` | `rasters.read` | Rasters | `Rasters.statistics` |
| `rasters.sample` | `rasters.read` | Rasters | `Rasters.sample` |
| `project.layer_ids` | `project.read` | Project (flat ids) | `Project.layer_ids` |
| `project.tree` | `project.read` | Project (the layer tree) | `Project.layer_tree` |
| `project.add_layer` | `project.write` | Project (the layer tree) | `Project.add_layer` |
| `project.remove_layer` | `project.write` | Project (the layer tree) | `Project.remove_layer` |
| `project.move_layer` | `project.write` | Project (the layer tree) | `Project.move_layer` |
| `project.set_visible` | `project.write` | Project (the layer tree) | `Project.set_visible` |
| `project.crs` | `project.read` | Project (CRS) | `Project.crs` |
| `project.set_crs` | `project.write` | Project (CRS) | `Project.set_crs` |
| `project.variables` | `project.read` | Project (variables) | `Project.variables` |
| `project.set_variable` | `project.write` | Project (variables) | `Project.set_variable` |
| `project.unset_variable` | `project.write` | Project (variables) | `Project.unset_variable` |
| `project.properties` | `project.read` | Project (custom properties) | `Project.custom_properties` |
| `project.set_property` | `project.write` | Project (custom properties) | `Project.set_custom_property` |
| `project.unset_property` | `project.write` | Project (custom properties) | `Project.unset_custom_property` |
| `project.bookmarks` | `project.read` | Project (bookmarks) | `Project.bookmarks` |
| `project.bookmark` | `project.read` | Project (bookmarks) | `Project.bookmark` |
| `project.add_bookmark` | `project.write` | Project (bookmarks) | `Project.add_bookmark` |
| `project.remove_bookmark` | `project.write` | Project (bookmarks) | `Project.remove_bookmark` |
| `project.read` | `project.write` | Project (the file) | `Project.read` |
| `project.write` | `project.write` | Project (the file) | `Project.write` |
| `project.save` | `project.write` | Project (the file) | `Project.save` |
| `project.changed` | `project.read` | Project (a push stream) | `Project.watch_changes` |
| `settings.get` | `settings.read` | Settings | `Settings.get` |
| `styles.apply` | `styles.apply` | Styles (a packaged QML, destructive) | `Styles.apply_style` |
| `symbology.get` | `symbology.read` | Symbology | `Styles.symbology` |
| `symbology.set` | `symbology.write` | Symbology (destructive) | `Styles.set_symbology` |
| `labelling.get` | `symbology.read` | Symbology (labelling) | `Styles.labelling` |
| `labelling.set` | `symbology.write` | Symbology (labelling, destructive) | `Styles.set_labelling` |
| `styles.list` | `styles.read` | Styles (the style manager) | `Styles.list_styles` |
| `styles.export` | `styles.read` | Styles (QML or SLD text) | `Styles.export_style` |
| `styles.import` | `styles.write` | Styles (QML or SLD text, destructive) | `Styles.import_style` |
| `files.export` | `files.export` | Files (authority) | `HostAuthority.export_file` |
| `blob.get` | `blob.read` | Payloads above the inline ceiling | `HostAuthority.read_blob` |
| `features.page` | `features.read` | Features (a bounded page stream) | `Features.page` |
| `features.get` | `features.read` | Features | `Features.feature` |
| `expressions.evaluate` | `expressions.evaluate` | Expressions | `Features.evaluate` |
| `expressions.validate` | `expressions.evaluate` | Expressions | `Features.check` |
| `editing.begin` | `features.edit` | Editing | `Features.begin_edit` |
| `editing.add` | `features.edit` | Editing | `EditingSession.add` |
| `editing.update` | `features.edit` | Editing | `EditingSession.update` |
| `editing.delete` | `features.edit` | Editing | `EditingSession.delete` |
| `editing.commit` | `features.edit` | Editing | `EditingSession.commit` |
| `editing.rollback` | `features.edit` | Editing | `EditingSession.rollback` |
| `algorithms.providers` | `algorithms.read` | Processing | `Algorithms.providers` |
| `algorithms.list` | `algorithms.read` | Processing | `Algorithms.list` |
| `algorithms.describe` | `algorithms.read` | Processing | `Algorithms.describe` |
| `algorithms.run` | `algorithms.run` | Processing | `Algorithms.run` |
| `layouts.list` | `layouts.read` | Layouts (the project's) | `Layouts.list` |
| `layouts.load_template` | `layouts.write` | Layouts (a template) | `Layouts.load_template` |
| `layouts.export` | `layouts.export` | Layouts (a render, destructive) | `Layouts.render` |
| `layouts.atlas` | `layouts.export` | Layouts (an atlas run, destructive) | `Layouts.render_atlas` |
| `notifications.info` | `notifications.info` | Notifications | `Notifications.info` |
| `network.fetch` | `network.fetch` | Network | `NetworkTransport.send` |
| `canvas.extent` | `canvas.read` | Canvas (the view) | `Canvas.extent` |
| `canvas.scale` | `canvas.read` | Canvas | `Canvas.scale` |
| `canvas.crs` | `canvas.read` | Canvas | `Canvas.crs` |
| `canvas.center` | `canvas.read` | Canvas | `Canvas.center` |
| `canvas.themes` | `canvas.read` | Canvas (map themes) | `Canvas.themes` |
| `canvas.extent_changed` | `canvas.read` | Canvas (a push stream) | `Canvas.watch_extent` |
| `canvas.zoom_to` | `canvas.control` | Canvas | `Canvas.zoom_to` |
| `canvas.refresh` | `canvas.control` | Canvas | `Canvas.refresh` |
| `canvas.apply_theme` | `canvas.control` | Canvas (map themes) | `Canvas.apply_theme` |
| `canvas.capture` | `canvas.control` | Canvas (a capture stream) | `Canvas.capture` |

Thirteen operations carry the `destructive` annotation, and nothing infers it from
a name: `project.read` (it replaces the open project), `project.write`,
`project.save`, `project.remove_layer`, `project.remove_bookmark`,
`project.unset_variable`, `project.unset_property`, `layouts.export` and
`layouts.atlas` (both replace a file the page's own write ref already names), and
`styles.apply`, `symbology.set`, `labelling.set` and `styles.import` (each
replaces how a layer is drawn, labelled or both - a packaged style is applied
*over* whatever the layer had, and a style document replaces the renderer and the
labelling together). The annotation is
declared beside the operation (`HostOperation.destructive`), crosses in the
manifest, and is the flag the agent consent list reads so a destructive tool can
be set to "ask each time" ([decision-49](../../decisions/decision-49%20-%20Expose-the-runtime-to-agents-over-a-loopback-transport-with-the-MCP-server-in-the-tools-for-developers-and-users-alike.md)
point 4, [decision-27](../../decisions/decision-27%20-%20Expose-curated-host-services-to-web-views-as-generated-namespaces.md)
point 2). `tests/test_bridge_host_project.py` pins the list, so adding one
without the annotation fails.

Two checks keep the table honest: `tests/scripts/test_service_coverage.py` fails
when an operation declared in `qgis_sdk.bridge.host.HOST_OPERATIONS` has no row
here, or when a row names an operation that no longer exists; and
`qgis-sdk check --grants` prints the same table for one project, with what the
page and the console actually reach. A service lands with its rows in the same
change (decision-54 point 1), so a later sprint adds rows here rather than a
second list somewhere else.

## Planned

The three 0.10.0 rows below are the services that landed in this release rather
than a later one: they stay in this table because their tasks are open on
something narrower than the service - the canvas on its server refusal, the
payloads on a measurement, the vocabulary on the deferred audit - and the status
column says what did land.

| Area | Service / operations | Task | Milestone | Status |
| --- | --- | --- | --- | --- |
| Canvas | `canvas.extent_changed` and `canvas.capture` are the two streams; a server refuses every operation by name | [TASK-85](../../tasks/task-85%20-%20Add-the-canvas-service-extent-scale-CRS-zoom-refresh-map-themes-extent-stream-and-capture-tools.md) | 0.10.0 | complete (the extent, zoom, themes, refresh and capture calls plus the two streams; a server refuses each by name, and doc-12, doc-13 and the example use `zoom_to`) |
| Layer kinds | mesh, point cloud, vector tile, annotation, tiled scene | [TASK-91](../../tasks/task-91%20-%20Add-mesh-point-cloud-vector-tile-annotation-and-tiled-scene-layer-kinds-with-per-kind-info-models-and-open-operations.md) | 0.11.0 | complete (the five kinds, their models, layer inputs and pickers, the Processing source-type narrowing and the five host operations); all five open natively - mesh over the checked-in `lagoon.2dm`, annotation by creation, and point cloud, vector tile and tiled scene over files `tests/layer_kind_fixtures.py` builds (a LAS 1.2 point cloud, an MBTiles source, a 3D Tiles `tileset.json`) rather than committing binaries the review cannot read; the release waits for the 0.11.0 gate |
| Connections / auth | `connections.list/describe/browse/open_layer/test`, `auth.configurations` (ids only) | [TASK-92](../../tasks/task-92%20-%20Add-connections-and-authentication-configuration-registered-data-source-connections-browsing-opening-from-a-connection-auth-configuration-ids.md) | 0.11.0 | planned |
| Symbology | `styles.symbology/set_symbology/labelling/set_labelling/list_styles/export_style/import_style`, renderers, symbols and labelling | [TASK-93](../../tasks/task-93%20-%20Add-symbology-labelling-and-the-style-manager-renderer-and-symbol-models-labelling-settings-style-manager-read-QML-and-SLD-import-and-export.md) | 0.11.0 | complete (four renderers - single symbol, categorized, graduated, rule-based - three symbols, one simple labelling, the style manager's three name lists and QML/SLD text both ways); the renderer union is curated on purpose (decision-16), QML reproduces the renderer and SLD reproduces the drawing, and `custom` is a *readable* graduated mode because QGIS reports it for a hand-banded layer; the release waits for the 0.11.0 gate |
| Processing breadth | multi-layer outputs, `run_model`, `batch`, help text rendering | [TASK-94](../../tasks/task-94%20-%20Widen-Processing-discovery-and-help-every-output-kind-model-files-and-batch-runs.md) | 0.11.0 | planned |
| Large payloads | `BlobRef`, `qgis.host.blob`, bounded pages, stream `ack` (decision-59) | [TASK-102](../../tasks/task-102%20-%20Carry-large-and-binary-payloads-by-reference-BlobRef-qgis.host.blob-bounded-pages-stream-backpressure-measured-defaults.md) | 0.10.0 | landed in 0.10.0 (the ref, the blob fetch, bounded pages and `ack`); the task stays open only for the cap and page-size measurement in a real `QWebEngineView` and decision-59's status review |
| Log | `ctx.log` debug/info/warning/error, correlation ids, agent log stream (decision-63) | [TASK-106](../../tasks/task-106%20-%20Add-ctx.log-crash-capture-into-it-the-Report-a-problem-surface-and-qgis-sdk-diagnose-with-no-telemetry.md) (minimum in [TASK-96](../../tasks/task-96%20-%20Add-surface-wiring-and-the-rest-of-the-native-catalogue-on-subscribe-ui-loading-behaviour-mixins-containers-feedback-Custom-and-the-fake-rendering.md)) | 1.0.0 | planned |
| i18n | `qgis.host.i18n` locale and strings (decision-60) | [TASK-103](../../tasks/task-103%20-%20Add-i18n-through-Qt-catalogues-shared-with-the-page-and-the-accessibility-rule-UI005.md) | 1.0.0 | planned |
| Grant vocabulary | `<service>.<operation>` across page, console and the HTTP allowlist; `check --grants` | [TASK-84](../../tasks/task-84%20-%20Unify-the-grant-vocabulary-across-web-agent-and-console-and-publish-the-service-coverage-map.md) | 0.10.0 | complete (the vocabulary, `[tool.qgis-sdk.console] grants`, the matrix, this map and `check --grants` landed; the agent consent and audit the decision listed are deferred with decision-49's withdrawal) |

## Proposals awaiting a decision

These are exploratory tasks, not accepted APIs or release commitments.

| Area | Proposal | Task | Target |
| --- | --- | --- | --- |
| Custom expressions | Plugin-owned registration of custom expression functions, separate from evaluate/validate | [TASK-128](../../tasks/task-128%20-%20Explore-owned-custom-QGIS-expression-function-declarations.md) | unassigned |
| QGIS validity checks | Owned registration and lifecycle of layout and other validity checks | [TASK-129](../../tasks/task-129%20-%20Explore-owned-QGIS-layout-and-other-validity-check-declarations.md) | unassigned |
| Attribute forms | Owned form configuration per field: editor widgets, aliases, defaults, constraints and layer actions, as a typed description | [TASK-149](../../tasks/task-149%20-%20Explore-attribute-forms-and-editor-widgets-as-a-service.md) | unassigned |
| Schema / fields | Field add/rename/delete/type on the features service, and whether the field calculator is an operation or a composition | [TASK-150](../../tasks/task-150%20-%20Explore-field-and-schema-management-on-the-features-service.md) | unassigned |
| Selection | Selection as a write: by ids, expression or extent, plus `clear` and a change stream; grant undecided | [TASK-151](../../tasks/task-151%20-%20Add-selection-as-a-writable-capability-with-a-change-stream.md) | unassigned |
| Map tools | Identify, measure, snapping, rubber bands, layer context-menu entries and layer signals, beyond `@tool` capture | [TASK-152](../../tasks/task-152%20-%20Explore-map-tools-and-layer-interaction-beyond-geometry-capture.md) | unassigned |
| Locator | A desktop-only locator-filter declaration with typed results and an activation that reaches an action | [TASK-153](../../tasks/task-153%20-%20Offer-locator-filters-as-a-plugin-declaration.md) | unassigned |
| Plugin-owned objects | One registration and ownership model for layer-tree indicators, property pages, canvas items, custom renderers, expression functions and validity checks | [TASK-154](../../tasks/task-154%20-%20Explore-plugin-owned-registration-of-QGIS-objects-the-SDK-does-not-model.md) | unassigned |
| Memory layers | Create and own a scratch layer so an intermediate result does not have to be written to disk | [TASK-155](../../tasks/task-155%20-%20Create-and-own-memory-layers-from-the-layers-service.md) | unassigned |
| Data sources | Provider plus datasource parameters behind `open_vector`, so PostGIS, WMS/WFS, XYZ, vector tiles and virtual layers are expressible | [TASK-156](../../tasks/task-156%20-%20Decide-how-the-SDK-opens-non-file-and-remote-data-sources.md) | unassigned |
| Map themes / visibility | Theme authoring and layer visibility, placed between the project and style services | [TASK-157](../../tasks/task-157%20-%20Place-map-theme-authoring-and-layer-visibility-between-project-and-styles.md) | unassigned |
| Temporal / 3D / diagrams | Explicit accept-or-decline for time filtering, 3D views and diagram renderers | [TASK-158](../../tasks/task-158%20-%20Decide-the-temporal-3D-and-diagram-surface.md) | unassigned |
| Documentation exit path | A going-deeper page, the two places the SDK contradicts PyQGIS advice, a troubleshooting page and a migration narrative | [TASK-159](../../tasks/task-159%20-%20Add-the-going-deeper-exit-pages-and-the-two-places-the-SDK-contradicts-PyQGIS-advice.md) | unassigned |

The eleven rows from `TASK-149` to `TASK-159` came out of the
[PyQGIS corpus coverage review](doc-31%20-%20PyQGIS-corpus-coverage-review.md),
which compares pyqgis.com's guide corpus with this map: each row is a capability
the corpus teaches that had no surface here *and* no task. None has a milestone,
an owner or a release; each closes with a recommendation, and a declined one
should end as a decision record rather than as silence.

See the [session synthesis](doc-28%20-%20Session-synthesis-worker-jobs-API-ergonomics-and-PyQGIS-safety.md)
for UI, dependency injection and other proposals and their status.

## Out of scope by decision

| Area | Why | Where recorded |
| --- | --- | --- |
| Raw `iface`, `eval`, arbitrary Qt objects over any boundary | authority model | decisions 9, 23, 48, 49 |
| `QgsTaskManager` as a public API | jobs are the API; the manager is the adapter | decision-53 |
| Mobile (QField) | not a host | decision-52 |
| Server deployment (FCGI, containers) | operator concern | decision-52 |
| Whole-window UI tree walks | `iface` proxy by the back door | decision-51 |

## Deferred without a task

Named so they are not forgotten; each needs its own decision before work
starts.

| Area | Note |
| --- | --- |
| Processing model designer integration | models run (TASK-94); authoring them is QGIS's UI |
| Native installers for standalone apps | conda recipe is the input ([decision-58](../../decisions/decision-58%20-%20Publish-plugins-to-the-official-QGIS-repository-from-the-tools-and-ship-standalone-apps-as-conda-packages.md)) |
| macOS QGIS row | unqualified until a leg exists ([decision-57](../../decisions/decision-57%20-%20Support-QGIS-4-LTR-and-latest-on-Linux-and-Windows-with-a-native-CI-leg-per-row-and-keep-QGIS-3-out-of-scope.md)) |

Map tools beyond point/line/polygon capture and 3D map views have left this
table: each now has an exploratory task in the proposals above
([TASK-152](../../tasks/task-152%20-%20Explore-map-tools-and-layer-interaction-beyond-geometry-capture.md),
[TASK-158](../../tasks/task-158%20-%20Decide-the-temporal-3D-and-diagram-surface.md)),
because the corpus review showed they were being rediscovered every session
rather than decided.
