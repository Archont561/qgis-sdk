---
id: doc-31
title: PyQGIS corpus coverage review
type: guide
created_date: '2026-11-06 09:40'
---
# pyqgis.com ↔ qgis-sdk: coverage review

A comparison of the pyqgis.com learning corpus against what this SDK documents
and actually implements, written to answer two questions: **what does the corpus
cover that the SDK does not**, and **where does the SDK go beyond it**.

*Method.* Fetched the home page, two path hubs and the whole sitemap (45 topic
hubs, several hundred guide pages; the site advertises "more than 350 in-depth
guides"). Compared that inventory against `doc-12` (Python guide), `doc-13`
(TypeScript guide), `doc-14` (workspace and qualification), `doc-22` (service
coverage map) and the code itself: the curated services in
`qgis_sdk.services`, the 34 host operations / 16 grants in
`qgis_sdk.bridge.host`, the thirty static-check rule ids documented in
`doc-12`, and the `qgis-sdk` command surface.

---

## 0. They are not the same genre, and that decides what "missing" means

pyqgis.com is a **breadth-first tutorial corpus for the raw PyQGIS API**: 45
hubs of recipes (`processing.run(...)`, `layer.renderer()...`, `QgsLayout...
addLayoutItem`). Its unit of value is *one working snippet for one API call*.

qgis-sdk is a **narrow, curated contract with a declared surface**: you get
`ctx.layers`, `ctx.canvas`, `@action`, `@job`, `@tool`, a fake for every service,
a grant vocabulary for pages, and generated TypeScript. Its unit of value is *a
capability that behaves identically on the fake, Desktop, the app window, the
server and a web page, and is testable without QGIS*.

So the honest framing is: the corpus maps ~100% of the PyQGIS surface at the
snippet level; the SDK deliberately implements a few percent of it and hides the
rest behind refusals-by-name. Every gap below is therefore a **decision to
revisit**, not an oversight — and the ones with a `TASK-nn` are already decided.

---

## 1. The corpus, by path

| Path | Hubs | Examples of what it teaches |
| :-- | :-- | :-- |
| Fundamentals & environment | 9 | API architecture, console, virtualenvs, PyCharm/VS Code + type stubs, debugging, headless/server automation, projects, features/geometries/memory layers, expressions |
| Spatial data processing & automation | 18 | vector ops, geometry predicates, CRS, attribute tables, raster, terrain, point cloud/PDAL, PostGIS, network analysis, spatial statistics, batch processing, algorithm chaining, layouts, atlas, web services, pandas/GeoPandas/rasterio |
| Cartography & visualization | 8 | styling, renderers, symbol layers, labelling, map themes, canvas export, temporal/3D, diagrams |
| Plugin development | 10 | boilerplate/lifecycle, Qt Designer, Processing providers, QgsTask, testing/CI, publishing, custom classes, attribute forms & layer actions, settings/i18n, custom map tools |

Against `doc-12`, that splits cleanly into three buckets: *already answered*,
*answered differently on purpose*, and *not answered*.

---

## 2. Coverage matrix (corpus hub → SDK today)

Legend: ✓ equivalent ground covered · ◐ partial / narrower · ✗ nothing ·
`n/a` out of scope by decision.

### Fundamentals

| Corpus hub | SDK today | Where |
| :-- | :-- | :-- |
| API architecture, signals/slots, object ownership | n/a by design | the SDK never hands out `qgis.core`/`qgis.gui` objects; `ctx` is the API. `doc-12` "Pure contract layer" documents the layering instead |
| Python console basics | ✓ | `doc-12` "From the QGIS Python console" — `plugin.console()`, `qgis_sdk.console.connect()`, `session.ctx`, `session.plugin(name)` |
| Virtual environments / install into QGIS | ◐ | the SDK's answer is the opposite of the corpus's advice: pip-installable, runtime vendored into the ZIP. `doc-12` "Supported targets", `qgis-sdk targets` |
| IDE setup, autocompletion, type stubs | ✗ | no guide, no stubs. Planned as exploration: TASK-133 |
| Debugging scripts | ◐ | `ctx.log` (4 levels, `LogView`), check rules, `qgis-sdk dev` reload. No debugging guide, no crash capture (TASK-106) |
| Headless QGIS / server automation | ◐ | server host ✓, app host ✓, `qgis-sdk run`. No Docker/cron/credentials/unattended-ops guide (deployment docs: TASK-101) |
| Projects | ◐ | `project.layer_ids`, `add_layer` only. CRS, variables, bookmarks, layer tree, save/read: TASK-88 |
| Features, geometries, memory layers | ◐ | features ✓ (paging, filters, 3 encodings), editing ✓. **No memory/scratch layer creation**; geometry models are encoded payloads, not `QgsGeometry` |
| Expressions | ◐ | `expressions.evaluate` / `validate` with a documented subset. **No custom function registration** (TASK-128, a proposal); no aggregate/context-scope surface |

### Automation

| Corpus hub | SDK today | Where |
| :-- | :-- | :-- |
| Vector data manipulation, geometry predicates | ◐ | reachable wholesale through `algorithms.run` / `qgis_sdk.processing.*`, not modelled per operation. No direct `Geometry` algebra (buffer/intersects) in the models |
| Attribute tables & field management | ✗ | editing writes features, not schema: no add/rename/delete/type field, no field calculator, no attribute join. **No task** |
| CRS | ◐ | CRS is carried on `VectorLayerInfo`, `CanvasExtent`, `CanvasPoint`; no transform/reproject API, no datum-transform choice. Project CRS: TASK-88 |
| Raster analysis | ✗ | TASK-87 (open/band/statistics/sample/export) |
| Terrain, spatial statistics, network analysis | ◐ | same as vector: `algorithms.run` covers the algorithms, no curated models |
| Point cloud / LiDAR | ✗ | TASK-91 (layer kinds), then algorithms only |
| PostGIS & databases | ✗ | `open_vector` is `QgsVectorLayer(path, ..., "ogr")` — **local files only**. Connections/auth: TASK-92 |
| Web services (WMS/WFS/WCS/XYZ/vector tiles/ArcGIS REST/OGC API) | ✗ | as above: no remote sources today; TASK-91 + TASK-92 |
| Python data stack (pandas/GeoPandas/shapely/rasterio) | ✗ | no interop helpers; encoded geometries make conversion DIY |
| Layouts, atlas, map series | ✗ | TASK-89 (planned for 0.10.0) |
| Batch processing, models, chaining | ◐ | single `algorithms.run` ✓, providers ✓, discovery ✓. Batch, models, help text, multi-layer outputs: TASK-94 |
| Data quality / topology validation | ✗ | algorithms only; no validation framework (TASK-129 is a proposal for validity checks) |

### Cartography

| Corpus hub | SDK today | Where |
| :-- | :-- | :-- |
| Styling, renderers, symbol layers | ✗ | `styles.apply_style` (host op `styles.apply`) takes a packaged QML string and nothing else. TASK-93 owns renderers/symbols/labelling |
| Labelling & annotations | ✗ | TASK-93 |
| Map themes & layer visibility | ◐ | `canvas.themes`, `canvas.apply_theme` ✓ (read + apply). **Creating** a theme or setting visibility: nothing, no task |
| Map canvas, image export, tiles | ◐ | `canvas` ✓ (extent/scale/crs/centre/zoom/refresh/themes/capture/extent stream). No canvas render-to-image, no PDF/SVG/tiles |
| Temporal & 3D | ✗ | nothing, no task (TASK-91 reads mesh/point-cloud layers, does not render 3D) |
| Diagrams & charts | ✗ | nothing, no task beyond TASK-93's scope |

### Plugin development

| Corpus hub | SDK today | Where |
| :-- | :-- | :-- |
| Boilerplate, lifecycle, metadata.txt, reload | ✓✓ | `qgis-sdk new` + runtime-owned lifecycle + `dev` reload + `build` rendering `metadata.txt` |
| Qt Designer, dialogs, docks, native widgets | ✓ | `doc-12` "Forms", "Desktop bindings and native surfaces", `.ui` support, `Component`/`Panel`/`Tabs` catalogue, snapshots |
| Processing providers | ✓ | `Provider` + `@algorithm`, `ctx.processing`, toolbox registration (TASK-39), parameter kinds incl. field/range/colour/enum (TASK-68) |
| Background tasks, progress, cancellation | ✓ (different model) | `@job` + named registry + `JobHandle` + `QgsTask` adapter; `QgsTask` is deliberately not public (decision-53) |
| Testing & CI | ✓✓✓ | the SDK's strongest area — see §4 |
| Publishing to the plugin repository | ◐ | `build` makes a compliant ZIP, but there is no publish command: TASK-100 |
| Custom classes (tree indicator, properties page, canvas item, renderer, provider) | ✗ | nothing, no task |
| Attribute forms & layer actions | ✗ | the SDK's `Form` is a *plugin action input window*, not a QGIS attribute form. Editor widgets, constraints, defaults, layer actions: **no task** |
| Settings & localisation | ◐ | `settings.get/set` (plugin prefix, versioned migrations). No options page in the QGIS Settings dialog, no translation (TASK-103) |
| Custom map tools & canvas interaction | ✗ | one shape of interaction: `@tool` capture of point/line/polygon. No measure, identify, snapping, rubber band, layer context-menu action, layer signals. **No task** |

---

## 3. Where the SDK already matches the corpus

Not a gap, but worth stating so the report is not all red:

- **Declarations + lifecycle**: `@plugin`/`@action`/`@stream`/`@job`/`@tool`,
  toolbar/menu/shortcut bindings, `initGui`/`unload` owned by the runtime, dev
  reload — the corpus's boilerplate + `classFactory` + reload hubs in one place.
- **Native UI**: the component catalogue, `.ui` files, the declarative form,
  `@on`/`@subscribe` wiring, and `build_surface` for QGIS-free tests.
- **Processing**: declaring your own algorithms *and* discovering/running anyone's
  (typed registry generated from a real QGIS snapshot).
- **Features/expressions/editing**: paging with a cursor, provider-side filters,
  three geometry encodings, expression evaluate/validate, explicit edit sessions.
- **Canvas**: extent/scale/CRS/centre/zoom/themes/capture with grants — including
  the parts the corpus has no equivalent for (the extent stream, capture as a
  declaration).
- **Console, HTTP allowlist, MCP**: three client surfaces over one vocabulary.

---

## 4. Where the SDK excels (no corpus equivalent)

1. **One contract, five backends.** Every service is a Protocol with a fake, a
   native adapter, host operations and a grant, and `doc-22` + `test_service_
   coverage.py` fail the build when a new operation has no row. The corpus teaches
   direct `QgsXxx` calls with no seam anywhere — its testing hub is five guides,
   one of which is "mock `iface`".
2. **QGIS-free testing as a first-class target.** `qgis-sdk test --target pure`
   installs an import guard that makes `import qgis` fail at collection, the
   native targets refuse a session where everything skipped, and the `server`
   target refuses a QGIS build without `qgis.server` instead of passing by skip.
   The corpus's equivalent advice is a `try/except` and a CI snippet.
3. **Native and web from one declaration.** 34 host operations behind 16 grants,
   `BlobRef` for oversized payloads, `ack`-based backpressure, a canonical
   fingerprint pinned in tests, and a generated `host.ts` with runtime
   validators — then stores plus React/Vue/Svelte bindings and web components.
   The corpus's plugin path is Qt-only; it has nothing on pages at all.
4. **Static project checks.** Thirty rule ids that encode the SDK's own
   invariants, not a formatter pass: `QGIS001`, `ARCH001`, `PROJECT001`/
   `PROJECT002`, `CONFIG001`, `META001`/`META002`, `ENTRY002`, `GRANT001`,
   `VERSION001`–`VERSION004`, `UI001`–`UI005`, `ICON001`, `JOB001`–`JOB003`,
   `HOST001`–`HOST003`, `SYNTAX001`, `DEP001`–`DEP004`. The corpus has one
   "lint and type check" guide.
5. **Authority as a vocabulary.** Page grants, console grants and the HTTP
   allowlist draw on one set of names, printed by `qgis-sdk check --grants`;
   capability probes (`ctx.has("canvas")`) and refusals-by-name replace
   attribute-guessing (`hasattr`) that the corpus's snippets rely on.
6. **UI as data.** Surface descriptions, YAML/PNG snapshots, `qgis-sdk ui
   list/open/snapshot/act`, a Storybook for the web mirror — a UI test harness.
   The corpus's UI hub ends at Qt Designer and "wire the signals".
7. **A real host matrix.** Desktop QGIS 4.2, QGIS 3.44 LTS (Qt5), a standalone
   `QgsApplication` app host and a QGIS Server host, qualified in CI; each
   service states what it does on each. The corpus's "port to QGIS 4 / Qt6" is a
   single guide about `exec_()` renames.
8. **Jobs as an API rather than a widget.** Named registry validated at startup,
   GUI-thread delivery, cancellation, ordering, and `quiesce()` so a dev reload
   can refuse to replace a revision with work in flight. The corpus's QgsTask hub
   is closer to DIY.
9. **Packaging that is testable.** `build` renders `metadata.txt` from
   `pyproject.toml`, vendors the runtime, and produces a ZIP; `targets` reports
   where the kit is qualified and where *this* host stands.
10. **Agent and console surfaces.** `qgis-sdk mcp` (development only),
    `plugin.console()`, `qgis_sdk.console.connect()`, and a grants matrix rendered
    for the author. The corpus's nearest is "run a script in the console".
11. **Documentation that is checked.** The four Gherkin features are linted by
    gherlint, every host operation must appear in `doc-22`, generated clients must
    be current, and each minor carries migration notes. Nothing in the corpus is
    machine-checked.

---

## 5. Where the SDK does not reach

### 5.1 Already decided — the backlog owns it

| Gap | Task | Milestone |
| :-- | :-- | :-- |
| Rasters: open/band/statistics/sample/export | TASK-87 | 0.10.0 |
| Project: CRS, variables, bookmarks, layer tree, save | TASK-88 | 0.10.0 |
| Layouts + atlas export | TASK-89 | 0.10.0 |
| Mesh, point cloud, vector tile, annotation, tiled scene layers | TASK-91 | 0.11.0 |
| Connections + auth configuration ids | TASK-92 | 0.11.0 |
| Symbology, labelling, style manager, QML/SLD both ways | TASK-93 | 0.11.0 |
| Processing breadth: batch, models, help, multi-layer outputs | TASK-94 | 0.11.0 |
| i18n through Qt catalogues | TASK-103 | 1.0.0 |
| `ctx.log` crash capture + `diagnose` | TASK-106 | 1.0.0 |
| Publish to plugins.qgis.org / private repositories | TASK-100 | — |
| App packaging + server deployment docs | TASK-101 | — |
| PyQGIS type stubs for authors | TASK-133 | exploration |
| Custom expression functions | TASK-128 | proposal |
| Layout/other validity checks | TASK-129 | proposal |

### 5.2 No task at all — the real findings

These are corpus areas with no SDK surface **and** no backlog item. Each now has
an **exploratory task** — a proposal, unmilestoned and unowned, not a release
commitment (the eleven landed as `TASK-149`–`TASK-159`; [doc-22](doc-22%20-%20Service-coverage-map.md)
lists them in one table). The numbering below is the review's, not the board's.

1. **Attribute forms and editor widgets** ([TASK-149](../../tasks/task-149%20-%20Explore-attribute-forms-and-editor-widgets-as-a-service.md)). Per-field widget configuration,
   value maps, range/relation widgets, defaults and constraints
   (`QgsEditorWidgetSetup`, `setFieldConstraint`). The corpus has five guides;
   the SDK has nothing, and its `Form` is a different thing (a plugin action's
   input window). This is the biggest single hole for "data entry tools".
2. **Schema and field management** ([TASK-150](../../tasks/task-150%20-%20Explore-field-and-schema-management-on-the-features-service.md)). Add/rename/delete/change-type fields, field
   calculator, attribute joins. The editing service writes *features* only, so an
   SDK plugin cannot prepare a layer it is about to write to.
3. **Selection as a write** ([TASK-151](../../tasks/task-151%20-%20Add-selection-as-a-writable-capability-with-a-change-stream.md)). `layers.selection(id)` reads; nothing selects by
   expression or by location, clears, or streams selection changes. Every
   "select then act" recipe in the corpus has no SDK spelling.
4. **Map tools beyond capture** ([TASK-152](../../tasks/task-152%20-%20Explore-map-tools-and-layer-interaction-beyond-geometry-capture.md)). Measure (`QgsDistanceArea`), identify, snapping
   (`QgsSnappingUtils`), rubber bands, layer context-menu actions, layer signal
   hooks. `@tool` covers three shapes and one callback; interaction is otherwise
   absent. (Layer context menus and signals are cheap, high-value additions.)
5. **Locator filters** ([TASK-153](../../tasks/task-153%20-%20Offer-locator-filters-as-a-plugin-declaration.md)). Registering an entry in QGIS's search box — a very common
   plugin feature with no SDK equivalent.
6. **Custom QGIS classes** ([TASK-154](../../tasks/task-154%20-%20Explore-plugin-owned-registration-of-QGIS-objects-the-SDK-does-not-model.md)). Layer tree indicators, layer property pages, custom
   canvas items, custom renderers/symbol layers, a Python data provider. All of
   these are "you must subclass a C++ class and register it" — exactly the kind
   of thing a contract layer could own, and today cannot.
7. **Memory/scratch layers** ([TASK-155](../../tasks/task-155%20-%20Create-and-own-memory-layers-from-the-layers-service.md)). No way to create a `memory:` layer, so a workflow
   that produces an intermediate table must write a file.
8. **Remote and non-file sources** ([TASK-156](../../tasks/task-156%20-%20Decide-how-the-SDK-opens-non-file-and-remote-data-sources.md)). `open_vector(Path)` is OGR-on-a-file only:
   WMS/WFS/WCS, XYZ, vector tiles, ArcGIS REST, OGC API, and PostGIS URIs are all
   unreachable, and neither TASK-91 (layer kinds) nor TASK-92 (connections)
   widens the open surface — a large corpus area hidden behind a signature that
   happens to take a `Path`.
9. **Map-theme authoring and layer visibility** ([TASK-157](../../tasks/task-157%20-%20Place-map-theme-authoring-and-layer-visibility-between-project-and-styles.md)). Reading and applying a theme
   works; creating one, or toggling layer visibility / scale-based visibility,
   has no surface and no task (it falls between TASK-88 and TASK-93).
10. **Temporal, 3D and diagrams** ([TASK-158](../../tasks/task-158%20-%20Decide-the-temporal-3D-and-diagram-surface.md)). Temporal controllers, time filters, 3D views, extrusion.
    Nothing, and nothing planned.
11. **Diagram and labelling configuration.** Labelling is folded into TASK-93;
    diagrams are not named anywhere and are now part of TASK-158.

### 5.3 Out of scope by decision (do not "fix")

Raw `iface`, `eval`, arbitrary Qt objects across a boundary; `QgsTaskManager` as
public API; mobile hosts. Recorded in `doc-22` and decisions 9, 23, 48, 49, 52,
53.

### 5.4 Two places where the corpus and the SDK disagree

Both are worth a paragraph in the docs, because a reader will hit them:

- **"Do not use a virtualenv; use QGIS's own interpreter."** True for scripts.
  The SDK ships a pip-installable kit that vendors its runtime *into the plugin
  ZIP* precisely to avoid that coupling — `doc-12` "Supported targets" says which
  QGIS/Qt each row pins, and `qgis-sdk targets` reports the local host.
- **"Mock `iface` to test."** The SDK's answer is a contract with fakes, plus a
  native target that refuses to pass by skipping. Mocking `iface` is what the
  SDK exists to remove — worth saying explicitly, since the corpus teaches it.

---

## 6. Documentation gaps (cheap, independent of API work)

These five are one docs task, [TASK-159](../../tasks/task-159%20-%20Add-the-going-deeper-exit-pages-and-the-two-places-the-SDK-contradicts-PyQGIS-advice.md),
because they share one reader — someone arriving from the corpus — and none of
them needs code.

The corpus is stronger than the SDK's guides at *task-oriented troubleshooting*.
Concrete things a reader of pyqgis.com gets and a reader of `doc-12` does not:

1. **A "what went wrong" page**: broken layer paths, invalid CRS, module import
   errors, `QgsGeometry` ownership, a check-rule id → fix. The SDK's check rules
   are thirty ids; `doc-12` lists them in a table but there is no troubleshooting
   walk-through (TASK-132 "discoverable check rule catalog" is adjacent).
2. **An IDE/typing page**: stubs, `target`-aware type-checking (TASK-133), what
   autocompletes and what cannot.
3. **A deployment page**: running an app-host plugin under a scheduler or in a
   container, and a server plugin on a real QGIS Server (TASK-101 owns this).
4. **A "going deeper" pointer list.** Because the SDK will never cover most of
   PyQGIS, `doc-12` should end with: "for anything not here, use raw PyQGIS —
   `ctx.desktop.iface` on Desktop, or write an adapter — and start at
   pyqgis.com/<hub>/". Right now the reader has no signposted exit.
5. **A migration-from-hand-written-plugin page**: 300 lines of
   `initGui`/`unload` → declarations, and what you lose (`iface` breadth) and gain
   (fakes, grants, pages).

---

## 7. Recommendations, ranked

**Do first (small, high return):**

1. **TASK-159** — the "going deeper" exit page for `doc-12`, linking the corpus
   hubs behind the biggest gaps, plus the two "we disagree with common advice"
   paragraphs (§5.4). One docs task, no code.
2. **TASK-151**, **TASK-155**, and the context-menu half of **TASK-152** — the
   three cheapest capability additions. Each appears in several corpus hubs and
   none needs a new backend. TASK-151 and TASK-155 are shaped as features;
   TASK-152 is a spike because the interaction surfaces have to be ranked first.

**Then decide (needs a call, not just work):**

3. **TASK-149** — attribute forms and editor widgets (§5.2.1), the largest
   missing capability for data-entry plugins. The proposal is a typed description
   (widget setup plus constraints) rather than a Qt widget escape hatch.
4. **TASK-154** — the registration model, which is the blocker under TASK-149,
   TASK-150 (schema), TASK-153 (locator) and the two older spikes TASK-128 and
   TASK-129. One decision opens four tasks.
5. **TASK-156** — non-file and remote sources (§5.2.8). Highest priority of the
   eleven despite being a spike: it is the only gap that makes a whole corpus
   path (PostGIS, WFS, XYZ, OGC API) unreachable, and it will not close by
   itself when TASK-91 and TASK-92 land.

**Leave as is:** raster/layout/layer-kind/connections/symbology work is already
scheduled. Temporal, 3D and diagrams should stay out of 1.x, but TASK-158 is how
they get *declined in writing* rather than forgotten again.

---

## 8. Caveats

- No QGIS or Qt in this workspace: nothing here was executed against a real QGIS.
  The claims are about *documented and declared* surface, cross-checked in code.
- pyqgis.com's 45 hubs were read as inventories; individual guide bodies were
  sampled, not read exhaustively. The hub and slug names are specific enough to
  place each topic.
- "No task" was checked by keyword across `backlog/tasks/` (editor widget,
  locator, select by, snapping, memory layer, field calculator, temporal, 3D,
  attribute form) and by reading task titles — not by exhaustively reading all
  ~170 task files.
- The eleven proposals that came out of §5.2 and §6 are `TASK-149`–`TASK-159`:
  unmilestoned, unowned, no release promised, each closing with a recommendation
  and naming its blockers. A declined one should become a decision record, not
  silence.
