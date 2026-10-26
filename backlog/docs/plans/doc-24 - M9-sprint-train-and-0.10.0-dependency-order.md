---
id: doc-24
title: M9 sprint train and 0.10.0 dependency order
type: guide
created_date: '2026-10-26 10:20'
---
# M9 sprint train and 0.10.0 dependency order

**Status:** Planning; starts after the TASK-83 gate. Orders work the m-9
tasks already declare; adds no scope. Sprint membership lives here and in the
milestone body ([doc-10](../doc-10%20-%20Backlog-conventions-vocabulary-statuses-and-predicates.md)).

## 1. Where m-9 starts from

The curated surface is the "Shipped" table of
[doc-22](doc-22%20-%20Service-coverage-map.md); everything in its "Planned"
table for 0.10.0 is `ctx.desktop.iface` today. Authority is three dialects.
([decision-54](../../decisions/decision-54%20-%20Cover-every-QGIS-service-and-layer-kind-through-the-contract-fake-native-host-grant-pattern-under-one-grant-vocabulary.md))

## 2. Dependency read

| Task | Declared dependencies | Startable |
| --- | --- | --- |
| [TASK-84](../../tasks/task-84%20-%20Unify-the-grant-vocabulary-across-web-agent-and-console-and-publish-the-service-coverage-map.md) grant vocabulary + coverage map | TASK-76, TASK-73 | after 0.8.0 |
| [TASK-86](../../tasks/task-86%20-%20Add-the-features-and-expressions-services-paged-iteration-filters-geometry-models-attribute-read-editing-sessions-evaluate-and-validate.md) features + expressions | TASK-84 | after 84 |
| [TASK-85](../../tasks/task-85%20-%20Add-the-canvas-service-extent-scale-CRS-zoom-refresh-map-themes-extent-stream-and-capture-tools.md) canvas | TASK-84, TASK-81 (app window) | after 84 |
| [TASK-87](../../tasks/task-87%20-%20Add-rasters-open-band-and-statistics-info-sample-at-point-export.md) rasters | TASK-84 | after 84 |
| [TASK-88](../../tasks/task-88%20-%20Extend-the-project-service-CRS-read-write-and-save-variables-custom-properties-bookmarks-and-the-layer-tree.md) project full | TASK-84 | after 84 |
| [TASK-89](../../tasks/task-89%20-%20Add-layouts-and-atlas-list-template-load-export-to-PDF-PNG-and-SVG-as-jobs-atlas-iteration-with-progress.md) layouts + atlas | TASK-84 | after 84 |
| [TASK-90](../../tasks/task-90%20-%20Prepare-and-qualify-0.10.0-release.md) 0.10.0 gate | TASK-83, 85–89 | release gate |

## 3. Sprint train

- **Sprint 1: TASK-84.** One vocabulary, console grants, `check --grants`,
  doc-22 as the enforced source of truth. Small; first because every later
  sprint fills the map.
- **Sprint 2: TASK-86.** Features, geometry models, paging, editing
  sessions, expressions. First real service because it settles the
  wire-model questions (geometry encodings, binary payloads, page bounds)
  that rasters and layouts reuse; the answers are written into decision-54's
  status review.
- **Sprint 3: TASK-85.** Canvas on Desktop and in the app window, `@tool`
  capture, the extent stream.
- **Sprint 4: TASK-87 with TASK-88.** Kinded `LayerInfo` and rasters; the
  full project service and layer tree in the same pull request (they share
  the `Layers.list` change).
- **Sprint 5: TASK-89.** Layouts and atlas as jobs on the task manager.
- **Gate: TASK-90.** `python-v0.10.0` paired with the next `ts-v*` minor
  (regenerated host manifest), one merge commit, explicit authorization.

## 4. Hygiene at sprint start

- Regenerate `generated/host.ts` and the fixtures with every sprint; never
  hand-edit; `HOST_FINGERPRINT` moves once per sprint and is shown.
- decision-27 status review (host surface grown beyond the 0.5.0 namespaces) with TASK-88.
