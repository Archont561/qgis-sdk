---
id: decision-16
title: Separate reusable layer styles from UI themes
date: '2026-10-16 08:05'
status: accepted
---
## Context

Map rendering and UI appearance are different capabilities; one generic styling service would mix GIS renderers with widget/CSS presentation.

## Decision

Proposed: GIS styles apply to layers but definitions/resources can be reusable. Start with packaged QML application through the layer service; introduce models/styles, a dedicated style service and native adapter only as real workflows justify it. Validate target layer/field/geometry compatibility, style resource safety and explicit CRS/scale semantics where relevant. Do not mirror the entire renderer API prematurely.

UI styling belongs to the UI theme system. Prefer inherited QGIS palette/appearance and carefully scoped QSS for native widgets; web frontends use CSS and semantic tokens. Do not change the application's global stylesheet or promise CSS/QSS feature equivalence. Theme subscriptions/resources follow view lifetime.

Algorithms produce headlessly usable data; optional output styling occurs through appropriate Processing post-processing/project-load handling, not GUI-owned layer mutation from a worker. Users can override default styling.

## Consequences

- Layer styles/resources and UI themes have separate contracts, models, adapters and tests.
- Rich declarative styles, token names, theme synchronization and exact ctx.styles/ctx.ui.theme APIs remain proposed rather than v1 commitments.

## Status review (2026-10-24): stays `proposed`

The layer-style half of this decision is now implemented and proven, so the
separation it asks for is no longer a plan (TASK-25.4):

- styles are requested by catalog identifier and resolved from the installed
  package (`qgis_sdk.resources`), never from an ambient path;
- one shared pure rule (`StyleSpec.incompatibilities`) decides compatibility, so
  the in-memory fake and the PyQGIS adapter cannot disagree;
- mismatches are refused before any QML is loaded, as a structured
  `QgisSdkStyleIncompatibleError` listing every reason;
- the application stylesheet and palette are proven unchanged across an
  application, by test and by the real-host harness - so layer styling genuinely
  does not touch UI theming.

**Why it still reads `proposed`:** the Consequences section says rich declarative
styles, token names, theme synchronization and the exact `ctx.styles` /
`ctx.ui.theme` APIs "remain proposed rather than v1 commitments", and none of them
exists. The *boundary* is accepted in practice; the *theme half of the contract*
does not exist yet, and promoting now would ratify an API surface nobody has
designed. Promote when a UI theme surface is defined, or amend this decision to
cover only the layer-style half that has landed.

## Status review (2026-10-26): theme half assigned to decision-46, stays `proposed`

The layer-style half is implemented as proposed: `styles.apply` through the
layer service applies packaged QML with compatibility checks, is one of the
curated host operations (decision-27) and has native service tests; no
separate style service was introduced because no workflow asked for one.

The UI-theme half had nothing to point at until decision-46, which narrows
it to the smallest useful thing: CSS variables on the web page seeded from
the running QGIS palette by `host()`, a `./ui` set of controls that read
them, and no change to the application's global stylesheet. Native widgets
keep inheriting the QGIS palette; no QSS is shipped. Rich declarative themes
and CSS/QSS equivalence stay out, as the Decision section already said.

**Promotion condition:** promote when TASK-70 lands the palette tokens and
`./ui`; the status review at that point names the variables as the theme
surface and this decision is read with that narrowing.

## Status review (2026-10-27): promoted to `accepted`; the palette tokens are the theme surface

TASK-70 landed the theme half, and it is exactly the narrowing the previous
review named. The UI theme surface of this SDK is the set of CSS custom
properties `@archont561/qgis-sdk-ui` publishes as `TOKEN_NAMES`, each read as
`--qgis-sdk-<name>`:

| Token | Palette role (`PALETTE_ROLES`) | Token | Palette role |
| --- | --- | --- | --- |
| `bg` | `window` | `accent-fg` | `highlightedText` |
| `fg` | `windowText` | `border` | `mid` |
| `surface` | `base` | `muted` | `placeholderText` |
| `surface-fg` | `text` | `link` | `link` |
| `control` | `button` | `danger` | fixed per side |
| `control-fg` | `buttonText` | `font`, `font-size`, `radius`, `space` | fixed per side |
| `accent` | `highlight` | | |

How it is read with this narrowing:

- **Seeded by the host, not styled by it.** `host()` carries the running QGIS
  palette in the handshake; `applyHostTheme(qgis)` turns it into the tokens
  through `PALETTE_ROLES` over the light or dark defaults and sets
  `data-qgis-sdk-theme`. A page outside QGIS keeps `tokens.css` (the light
  defaults on `:root`, the dark ones under the attribute). The application's
  global stylesheet is never touched; native widgets inherit the QGIS palette
  and no QSS ships.
- **One stylesheet, any palette.** `dist/style.css` is compiled from the
  package's own `qs-` utilities and binds every colour, font and radius to a
  token, so switching palettes - the host's, or the Storybook toolbar's -
  needs no rebuild. A consumer's `./uno` preset builds the same tokens.
- **Layer styles stay on the other side of the line.** `styles.apply` applies
  packaged QML to layers with compatibility checks; it reads no token and the
  tokens read no renderer. Rich declarative themes, CSS/QSS equivalence and a
  `ctx.ui.theme` API remain out of scope, as the Decision section says.

The Consequences hold as written: separate contracts, models, adapters and
tests for the two halves. The second consequence is now settled rather than
open - the token names above are the committed surface, and renaming one is a
breaking change of `qgis-sdk-ui`.

## Status review (2026-11-07): symbology lands inside the same boundary, stays `accepted`

TASK-93 added the half of this decision the first review left open in practice:
"introduce models/styles, a dedicated style service and native adapter only as
real workflows justify it". A real workflow asked for it (decision-54 point 4:
symbology, labelling and the style manager behind the curated surface), so the
`Styles` protocol grew from one method to eight - `apply_style`, `symbology`,
`set_symbology`, `labelling`, `set_labelling`, `list_styles`, `export_style`,
`import_style` - with one fake, one PyQGIS adapter and seven host operations. The
boundary this decision drew is unchanged:

- **Layer styles and UI themes still do not meet.** No call here reads the
  application palette or its stylesheet, and `test_native_styles_theme.py` still
  proves the theme is byte-identical across an application.
- **Nothing mirrors the renderer API.** Four renderers of QGIS's sixteen
  (single symbol, categorized, graduated, rule-based), three symbols rather than a
  symbol-layer tree, and one simple labelling. The curated set is named once
  (`RENDERER_KIND_NAMES`, `SYMBOL_KINDS`, `GRADUATED_MODES`, `MARKER_SHAPES`) and
  the wire carries `kind` as the discriminator, so a page narrows rather than
  guesses.
- **What is not modelled is refused by name, not approximated.** A heatmap, a
  nested rule group, an else rule, a rule with no symbol, a rule-based labelling,
  a symbol its geometry cannot draw, and a style-manager kind outside the three
  all raise rather than being described as the nearest thing they resemble. That
  is the same rule `StyleSpec.incompatibilities` follows for a packaged QML, and
  the geometry check is one shared helper (`symbol_fits_geometry`) so the fake and
  the native adapter cannot disagree.
- **Compatibility is still decided before anything is applied.** A packaged QML
  is validated against the layer before it is loaded, and a symbol is checked
  against the layer's geometry before a renderer is built.
- **Explicit formats, no sniffing.** QML and SLD cross as `StyleText` with a
  `format` the caller states; the host does not guess from the first character.

Two readings are recorded here because they are the ones a later change could
get wrong:

1. **QML reproduces the renderer; SLD reproduces the drawing.** QGIS's SLD export
   writes one rule per category and its importer reads that back as a rule-based
   renderer, so a categorized renderer cannot survive SLD as itself. The contract
   therefore asserts exact equality for QML and the painted colours for SLD, and
   the guides say so rather than promising a round trip SLD cannot keep.
2. **`custom` is a readable graduated mode.** QGIS reports
   `QgsClassificationCustom` for a renderer whose ranges were edited by hand -
   an ordinary layer, not an error - so refusing it would make `symbology()` fail
   on any hand-banded layer. It is last in `GRADUATED_MODES` because it is an
   answer the adapter reads, not a classification a caller asks QGIS to compute.

The Consequences still hold and are now broader rather than looser: separate
contracts, models, adapters and tests for the layer-style and UI-theme halves;
rich declarative styles, token names, theme synchronization and a `ctx.ui.theme`
API remain out of scope. The status stays `accepted` - this review extends the
decision to symbology, it does not reopen it.
