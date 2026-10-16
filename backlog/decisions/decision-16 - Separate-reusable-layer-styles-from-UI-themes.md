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
