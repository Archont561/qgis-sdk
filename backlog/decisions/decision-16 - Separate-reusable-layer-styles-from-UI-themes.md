---
id: decision-16
title: Separate reusable layer styles from UI themes
date: '2026-10-16 08:05'
status: proposed
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
