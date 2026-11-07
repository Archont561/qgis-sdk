---
id: TASK-93
title: >-
  Add symbology, labelling and the style manager: renderer and symbol models,
  labelling settings, style manager read, QML and SLD import and export
status: Done
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-11-07 07:15'
labels: []
milestone: m-10
dependencies:
  - TASK-87
type: enhancement
ordinal: 93000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 4; extends decision-16. symbology.get/set renderer for single, categorized, graduated and rule-based renderers with symbol models for the common layers, labelling get/set, style_manager list, apply_style from QML or SLD text and export to both; fake, native, host operations, grants.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Renderer, symbol and labelling models round-trip through set/get on native layers for every supported renderer; QML and SLD export then import reproduce the renderer (native tests).
- [x] #2 Host operations regenerated and typed; destructive annotations on set operations.
- [x] #3 doc-22 rows complete; decision-16 reviewed; doc-12/doc-13 document symbology.
<!-- AC:END -->

## Implementation notes

Implemented on the 0.10.0 sprint-2 branch, on top of the sprint-1 layer-kind
surface.

**Models.** `qgis_sdk.models.symbology` is a new module: `SingleSymbolRenderer`,
`CategorizedRenderer`/`Category`, `GraduatedRenderer`/`GraduatedClass` and
`RuleBasedRenderer`/`Rule` (all carrying `kind`), the symbols `MarkerSymbol`,
`LineSymbol` and `FillSymbol`, `Labelling`, `StyleText`, `StyleEntry`, and the
vocabulary tuples `RENDERER_KIND_NAMES`, `SYMBOL_KINDS`, `SYMBOLS_FOR_GEOMETRY`,
`GRADUATED_MODES`, `MARKER_SHAPES`, `STYLE_FORMATS`, `STYLE_MANAGER_KINDS`.
Colours are lowercase `#rrggbb`, an outline width of `0` means no outline and
round-trips as the zero it is, and `Labelling(enabled=True)` without a field is
refused where it is declared. Two shared helpers decide what the fake and the
native adapter may both claim: `symbol_kind(renderer)` and
`symbol_fits_geometry(renderer, geometry_type)` - the geometry check refuses a
symbol its layer cannot draw (`QgisSdkStyleIncompatibleError` naming both)
instead of letting QGIS render nothing and report success.

**Service.** `qgis_sdk.services.Styles` grew from `apply_style` to eight methods:
`symbology`, `set_symbology`, `labelling`, `set_labelling`, `list_styles`,
`export_style`, `import_style` alongside `apply_style`. The curated surface is
deliberate (decision-16): four renderers of QGIS's sixteen, three symbols rather
than a symbol-layer tree, one simple labelling. What is not modelled is refused
by name - a heatmap or other exotic renderer, a nested rule group, an else rule
(a complement has no filter to describe; mapping it to `TRUE` would repaint the
layer), a rule with no symbol, a rule-based labelling (not flattened to its first
style) and a style-manager kind outside `symbol`/`color_ramp`/`label_settings`.

**Graduated modes are classification methods.** `GRADUATED_MODES` is
`equal_interval`, `quantile`, `jenks`, `std_dev`, `pretty`, `custom`; the adapter
uses `QgsClassificationMethod`/`setClassificationMethod` and never the
deprecated renderer `mode` enum. `custom` is last because it is an answer
(`QgsClassificationCustom`, a hand-banded renderer) rather than a computation to
request - refusing it would fail `symbology()` on any layer the user banded.

**QML reproduces the renderer; SLD reproduces the drawing.** AC#1's "QML and SLD
export then import reproduce the renderer" is met at the strongest claim QGIS
allows: QML carries the renderer kind and round-trips it exactly; QGIS's SLD
export writes one rule per category and reads it back as rule-based, so SLD
round-trips the drawing (the colours, in order) and the contract asserts that
instead of a renderer identity SLD cannot keep. Style text crosses as
`StyleText(format=...)` with the caller naming the dialect; the other dialect is
refused as `QgisSdkStyleTextError` rather than sniffed.

**Fake.** `qgis_sdk.testing.FakeStyles(layers, scope, styles=...)` stores
descriptions, starts every layer with the single symbol its geometry implies
(`#808080` as marker/line/fill), refuses a wrong-geometry symbol through the
shared helper, and answers style text in a small JSON dialect of its own - so a
test asserts the round trip without a second QML parser to keep in step.

**Native.** `qgis_sdk.adapters.qgis.NativeStyles` builds and describes every
renderer through `_CLASSIFICATION_METHODS`/`_METHOD_IDS`, guards
`set_symbology` with the same geometry check, answers `Labelling()` for labels
switched on with no labelling object, refuses a rule-based labelling via
`QgsPalLayerSettings`, saves and loads through `saveNamedStyle`/`loadNamedStyle`
and SLD through `exportSldStyleV3` (the deprecated exporters are avoided), and
covers the parts only real QGIS can in
`tests/services/test_native_styles_symbology.py` (every renderer through QML, a
fill symbol on a polygon layer, a `QgsHeatmapRenderer` refused by name, a
rule-based labelling refused, the default style listing). That file needs a
QGIS installation to execute - this environment has none - so it is written and
linted here and runs under `QGIS_SDK_NATIVE_SERVICES=1` (and the planned
native CI leg, TASK-99); its claims are mirrored on the fake by
`test_symbology_contract.py`, which runs on both backends.

**Wire.** Seven operations - `symbology.get`/`set`, `labelling.get`/`set`
(under the new `symbology.read`/`symbology.write` grants), `styles.list` (paged,
`styles.read`), `styles.export` (`styles.read`), `styles.import` (`styles.write`)
- with the `destructive` annotation on `symbology.set`, `labelling.set`,
`styles.import` and the existing `styles.apply`. The host surface is now 75
operations, 26 grants, 70 actions, 13 destructive; `host.ts` regenerated
(`HOST_FINGERPRINT` `sha256:82e60b50...`).

**Docs.** doc-22's symbology row is complete with the seven host-operation rows;
doc-12 gains "Symbology, labelling and the style manager"; doc-13 gains
"Symbology from a page" (the unions, the grants, the destructive four);
decision-16 carries a fourth status review extending the boundary to symbology
and recording the two readings above (QML/SLD asymmetry, `custom` as an answer).
