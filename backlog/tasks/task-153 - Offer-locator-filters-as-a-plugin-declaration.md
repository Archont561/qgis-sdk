---
id: TASK-153
title: Offer locator filters as a plugin declaration
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/declarations/__init__.py
  - packages/qgis-sdk-tools/src/qgis_sdk_tools/check/hosts.py
priority: low
type: feature
ordinal: 153000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
QGIS's locator bar (the search box) is a first-class plugin surface with no SDK equivalent: a plugin cannot register a search prefix, and there is no model for a result with a title, a description, a bounding box and an activation. The corpus's custom-classes hub covers it; the board does not.

This proposal adds one desktop-only declaration - a prefix, a search callback answered with typed results, and an activation that reaches a declared action - with the ownership rules the rest of the runtime already uses, so unloading a plugin cannot leave a filter behind.

Unmilestoned proposal: no release is promised.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The declaration is typed and QGIS-free in author code: a prefix, a search that answers with results (title, description, optional bounds, an opaque id) and an activation that dispatches a declared action with that id; no `QgsLocatorFilter` subclass appears in a plugin.
- [ ] #2 Ownership is proven: registration on load, cleanup on unload, a second plugin claiming the same prefix is reported rather than silently shadowing the first, and a failed registration leaves nothing behind.
- [ ] #3 A `.check` rule (or an existing rule extended) refuses a locator declaration in a plugin that does not declare the `desktop` host, mirroring `HOST001`.
- [ ] #4 Fake and native agree: a fake that records registered prefixes and dispatches a query answers the same contract tests as the native adapter, and a desktop-marked test proves the native registration against a real `iface`.
- [ ] #5 doc-12 documents it, doc-22 gains the row with its grant, and the refusal on a server or app host names the reason.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Today the SDK has no locator surface: `qgis_sdk.declarations` exports plugin/action/stream/form/job/tool and `qgis_sdk.ui` a widget catalogue; `QgsLocatorFilter` does not appear anywhere in the packages. The closest precedent for the declaration shape is `@tool` (TASK-85): desktop-only, registered by the runtime, refused by name where the host has no canvas.

Untested hypothesis this task must not assume away: whether `iface.registerLocatorFilter` keeps the filter alive as a Python object, and what a fast-filter flag costs on a large layer. That is the first measurement.
<!-- SECTION:NOTES:END -->
