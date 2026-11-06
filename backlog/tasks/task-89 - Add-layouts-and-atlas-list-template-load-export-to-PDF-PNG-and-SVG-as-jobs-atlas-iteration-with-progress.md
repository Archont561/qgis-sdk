---
id: TASK-89
title: >-
  Add layouts and atlas: list, template load, export to PDF, PNG and SVG as
  jobs, atlas iteration with progress
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-06 18:00'
labels: []
milestone: m-9
dependencies:
  - TASK-84
type: enhancement
ordinal: 89000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. layouts.list, load_template(FileRef), export(layout_id, format, FileRef, settings) as a @job with progress and cancellation (QgsLayoutExporter), atlas.run(layout_id, FileRef pattern) as a job yielding one FileRef per page; fake, native, host operations, grants; export files are owned temporary outputs or author-granted paths.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Export and atlas run as jobs visible in the task manager, produce the files, report progress and cancel cleanly, with fake and native sharing the contract tests (native tests, offscreen rendering).
- [x] #2 Host operations regenerated and typed; the page and the agent receive FileRefs, never paths; the destructive annotation covers overwrite.
- [x] #3 doc-22 rows complete; doc-12/doc-13 document layouts; the example exports a PDF.
<!-- AC:END -->

## Implementation notes

Implemented as sprint 5 of the 0.10.0 train, on top of the sprint-4 services.

**One split, made deliberately.** The curated Protocol is
`qgis_sdk.services.layouts.Layouts` and holds no QGIS and no job machinery: the
`Layouts` and `LayoutBackend` protocols, the two job ids (`layouts.export`,
`layouts.atlas`), `NullProgress`/`NullCancellation`, and the shared helpers a
fake and a native adapter must answer identically (`exported`, `atlas_pages`,
`page_path`, `stop_if_cancelled`, `free_layout_name`, `_slug`,
`_check_pattern`). Everything that needs a `JobService` lives one layer up in
`qgis_sdk.layouts.LayoutService`, which both adapters subclass, so the policy a
caller sees - which thread resolves a ref, where a destination-less export
lands, what a job is titled - is written once. `test_pure_imports.py` pins the
layers.

**Jobs.** `export()` and `run_atlas()` build a plain `LayoutRequest` /
`AtlasRequest` on the driving thread - resolving the `FileRef` there, where the
files service may be read - and submit a `@job` whose body is a closure over the
backend and that request. The desktop worker backend runs it as one `QgsTask`,
so the export is a named row in the QGIS task manager, its bar follows
`ctx.progress` and its cancel button asks the job to stop. `render()` and
`render_atlas()` are the same work inline, for the host operations and for a
script. Progress is per page; cancellation is checked between pages, and a
cancelled job raises `QgisSdkJobCancelledError` and publishes no partial file.

**Models.** `qgis_sdk.models.layouts` holds `LayoutSettings`, `AtlasInfo`,
`LayoutInfo`, `LayoutExport`, `AtlasPage`, `AtlasExport`, the two request shapes
and the wire schemas. A layout is named by its own name (QGIS keeps them unique
in a project); a PNG or SVG of a multi-page layout is refused by name rather
than written as "the first page"; an atlas page counts from one and names the
coverage feature it was drawn for.

**Native.** `QgsLayoutManager` for `list`/`load_template` (a `.qpt` is read
through `QFile` → `QDomDocument` → `loadFromTemplate`, named after the file's
stem with `free_layout_name` for a collision), `QgsLayoutExporter` for the two
renders with its three settings classes built per format, and
`QgsLayoutAtlas.beginRender`/`seekTo`/`endRender` for the iteration - the
exporter's own multi-file overloads name files from the layout's file-name
expression, which would put a project setting between the caller's pattern and
the disk. The exporter's `ExportResult` decides what a caller hears: `Canceled`
becomes `QgisSdkJobCancelledError`, everything else `QgisSdkExportFailedError`
carrying `errorMessage()`/`errorFile()`.

**Fake.** `qgis_sdk.testing.FakeLayouts` declares layouts and coverage ids and
writes a short marker file per format (the PDF magic, the PNG signature, an
`<svg>` root) through `qgis_sdk.exports`, so refusals, staging and commit are
the native adapter's own code path.

**Host.** Four operations - `layouts.list` (`layouts.read`),
`layouts.load_template` (`layouts.write`, it edits the project),
`layouts.export` and `layouts.atlas` (both `layouts.export`, both
`destructive` because they replace the file the page's write ref names). They
answer the blocking render forms: one request that ends with the file. Every
answer is a ref minted for the calling view (`file`, or `directory` plus one
`file` per page), and a destination arrives as the view's write ref, is
resolved against the binding and re-minted for the plugin's own files service.
`HOST_FINGERPRINT` moved once (`sha256:9aa12425...`); `generated/host.ts` and
the bridge cases were regenerated, never hand-edited. The two job forms are in
`DEFERRED_HOST_METHODS` because the wire has no way to follow a job.

**Contexts.** `PluginContext.layouts` is a GUI-bound capability: the two job
forms submit the render themselves, so a job body never needs to reach one.
Desktop and the app host pump the layouts service's `JobService` beside the
plugin's own, and the pump is skipped when the process has no Qt bindings - a
fake-backed pure test drives its jobs by hand.

**Docs and example.** doc-22 carries the layouts row, the four operations, the
grants and the nine-operation destructive list; doc-12 gained "Print layouts and
atlases" and doc-13 "Print layouts from a page"; decision-27 carries a second
status review (63 operations, 22 grants). `examples/simple` exports a PDF:
`LocalGisWorkflow.print_layout` plus the `export_layout` action, with two pure
tests over the fake.

**Evidence.** `tests/services/test_layouts_contract.py` (21 tests, fake and
native over the same fixture project), `tests/test_bridge_host_layouts.py` (10),
`tests/test_layout_models.py` (23),
`tests/features/layout_exports.feature` (12 scenarios, driven by
`tests/service_steps.py`), `tests/test_service_bdd.py` 26 passed, the full
Python suite 2686 passed / 107 skipped, `ruff check` and `ruff format` clean and
`check-gherkin` at 9 feature files. The native contract legs run in the
`QGIS_SDK_NATIVE_SERVICES=1` job: this sandbox has no PyQGIS, so the offscreen
`QgsLayoutExporter` path is exercised there and not here.
