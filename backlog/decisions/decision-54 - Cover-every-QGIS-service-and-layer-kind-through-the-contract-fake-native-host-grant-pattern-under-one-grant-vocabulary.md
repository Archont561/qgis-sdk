---
id: decision-54
title: Cover every QGIS service and layer kind through the contract-fake-native-host-grant pattern under one grant vocabulary
date: '2026-10-26'
status: accepted
---
## Context

The curated surface is workflow-shaped and vector-only: layers (vector open,
list, selection ids, export), flat project layer ids, settings, packaged QML
styles, Processing `execute`, network, notifications, workers. Absent:
canvas and map tools, features/attributes/expressions, rasters, layouts and
atlas, layer tree, project CRS/save, symbology beyond QML, mesh, point
cloud, vector tile, annotation and tiled-scene layers, providers and
connections, authentication, Processing discovery/outputs/models/batch.
Everything absent means `ctx.desktop.iface`, which forfeits fakes, bridge,
console, agent and authority. The owner wants all services and all layer
kinds covered. Authority is also three dialects today (web grants, agent
grants plus consent, console unrestricted).

## Decision

1. **The completeness rule.** A service exists only when all six parts land
   together: a Protocol in `services/`, plain models in `models/` (no native
   handle crosses), an in-memory fake in `qgis_sdk.testing` sharing the
   contract tests, a native adapter under `adapters/qgis/`, host operations
   in `bridge/host.py` with a regenerated manifest, and grants. A partial
   service is refused at review, not merged as "native-only for now".
2. **One grant vocabulary.** Operation ids are `<service>.<operation>`
   everywhere; `[tool.qgis-sdk.web] grants`, `[tool.qgis-sdk.agent] grants`
   and a new `[tool.qgis-sdk.console] grants` (default: everything, because
   the console is the plugin's own developer) use the same names, the same
   unknown-grant finding and the same `register_host_operations(only=)`.
   Destructive operations carry an annotation the agent consent list and
   the audit log use. `qgis-sdk check --grants` prints the matrix client ×
   operation.
3. **Services II (0.10.0).** `canvas` (extent, scale, CRS, center/zoom-to
   layer, selection or extent, refresh, map themes, an `on_extent_changed`
   stream; capture tools as a `@tool` declaration with point/line/polygon
   results), `features` (iterate with a bounded page size and server-side
   filters, get by id, geometry as WKB/WKT/GeoJSON models, attribute read;
   `expressions.evaluate`/`validate`; editing as an explicit session with
   commit/rollback), `rasters` (open, info with bands/no-data/statistics,
   sample at point, export), `project` (CRS, read/write/save, variables,
   custom properties, bookmarks, layer tree groups/visibility/order,
   `add_layer` into a group), `layouts` (list, template load, export to
   PDF/PNG/SVG as a job returning `FileRef`, atlas iteration as a job with
   progress).
4. **Layer kinds, providers, symbology, Processing breadth (0.11.0).**
   `LayerInfo` grows a `kind` with per-kind info models (`mesh`,
   `point_cloud`, `vector_tile`, `annotation`, `tiled_scene`) and open
   operations for each; `connections` (registered data-source connections,
   browse, open a layer from a connection; `auth` as configuration ids,
   never secrets) over the provider registry; `symbology` (renderer and
   symbol models for the common renderers, labelling settings, style
   manager read, QML/SLD import and export); Processing discovery (`list`,
   `describe` with help), every output kind, model files, batch runs.
5. **A coverage map is the source of truth.** doc-22 lists area → service →
   operations → fake → native → host → grant → status, is updated in the
   same change as any service work, and is what "all services covered"
   means at the 1.0 gate. An area not in the map is out of scope by
   decision, not by omission.
6. **Bridge impact is a minor per batch.** New host operations move
   `HOST_FINGERPRINT` and regenerate `generated/host.ts`; each services
   milestone releases one bridge minor with the regenerated manifest and
   the typed `qgis.host` additions; the wire protocol does not change.

## Consequences

- Authors stop reaching for `iface` for ordinary GIS work; the same
  operations are available to the page, the console and agents under one
  vocabulary.
- Two milestones of contract + fake + native + host + grant work (m-9,
  m-10), each releasing Python and a bridge minor from one gate; the
  wire-model questions (features, geometry, binary payloads, paging) are
  answered in the first batch.
- decision-16 (styles) and decision-27 (host surface) extend; the vector-only
  `VectorLayerInfo` of the 0.5.0 contract becomes the kinded `LayerInfo`
  (additive: the vector shape keeps its fields).
- Tasks: TASK-84 (grant vocabulary and coverage map), 85–89 (services II),
  gate 90; 91–94 (layer kinds, connections, symbology, Processing breadth),
  gate 95.
