---
id: TASK-86
title: >-
  Add the features and expressions services: paged iteration, filters, geometry
  models, attribute read, editing sessions, evaluate and validate
status: In Progress
assignee: []
created_date: '2026-10-26T10:11:00Z'
updated_date: '2026-10-31 00:00'
labels: []
milestone: m-9
dependencies:
  - TASK-84
  - TASK-102
type: enhancement
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-54 point 3. features.iterate(layer_id, filter=, fields=, page=) with a bounded page size and server-side QgsFeatureRequest filters, get(id), geometry as WKB/WKT/GeoJSON models, attributes as plain values; editing as an explicit session (begin, add/update/delete, commit, rollback) that is view-owned; expressions.evaluate(layer_id, text, feature_id?) and validate(text); fake, native, host operations, grants; the wire-model answers for features, geometry, binary payloads and paging recorded in decision-54's status review.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Iteration pages deterministically over fake and native layers with server-side filters and bounded size; geometry round-trips in all three encodings. Editing commits or rolls back for supported provider configurations, refuses or clearly reports unsupported guarantees, and is disposed with its view; native and stateful tests define the evidence.
- [x] #2 The host operations stream pages to the page under a grant with the bounded size enforced, evaluate/validate work from the console and the agent, and the regenerated manifest is typed in generated/host.ts.
- [x] #3 doc-22 rows complete; doc-12/doc-13 document the service, paging limits and tested provider-specific atomicity boundaries.
- [x] #4 Decide whether a Python context-manager convenience complements explicit sessions; specify already-editing and nested sessions, commit and rollback failure, cancellation, scope closure, undo and concurrent changes, without promising multi-provider atomicity unsupported by the host.
- [x] #5 Assess Pythonic feature, geometry part and vertex iteration including empty, multipart, wrong-type and invalid-index behavior; specify supported forms and bounded wire paging, compare native QGIS 4, and test fake/native behavior.
<!-- AC:END -->

## Implementation notes

Implemented on `arena/51fd063a-qgis-sdk` (0.10.0, sprint 2), together with
TASK-102.

**Models and contract.** `qgis_sdk.models.features` holds QGIS-free value types:
`Geometry` (encoding `wkb`/`wkt`/`geojson`, `geometry_type`, `crs`,
`part_count`, `vertex_count`, `is_empty`), `Feature`, `FeatureQuery`
(`limit`/`cursor`/`expression`/`bbox`/`ids`/`encoding`/`with_geometry`, refusing
a limit above `MAX_FEATURE_PAGE` = 1000 and defaulting to 100), `FeaturePage`
(`items`, `truncated`, `next_cursor` = the last feature id), `ExpressionOutcome`,
`ExpressionCheck` and `EditOutcome`. `services.features` declares the `Features`
and `EditingSession` Protocols; `qgis_sdk.testing` ships `FakeFeatures` (with
`FakeLayer`, `FakeEditingSession` and the documented expression subset in
`testing.expressions`) and `ctx.features` is on `PluginContext`/`UiContext`.

**Native.** `adapters.qgis.features.NativeFeatures` answers with
`QgsFeatureRequest` (`$id > cursor` paging, server-side `setFilterExpression`,
`setFilterRect`, `setFilterFids`), `QgsExpression` in a prepared context, and the
layer's own edit buffer. A commit reports `committed` and the provider's message
on failure; it never claims atomicity, because QGIS wraps a commit in a
transaction only for providers that implement one.
`adapters.qgis.context` wires it to the plugin context.

**Host.** Eleven operations were added (`features.page` as a stream,
`features.get`, `expressions.evaluate`, `expressions.validate`,
`editing.begin/add/update/delete/commit/rollback`), taking `HOST_OPERATIONS` to
24 and moving `HOST_FINGERPRINT`; `generated/host.ts` was regenerated. Grants
`features.read`, `expressions.evaluate` and `features.edit` are new. Sessions are
view-scoped through `Dispatcher.register_editing(close=, close_view=)`, so
`dispose(view)` closes what the view began and a session id from another view is
refused as `unknown_handle`. `HostServices.features` is optional: without it the
operations fail by name rather than answering with nothing.

**Evidence.** `tests/services/test_features_contract.py` runs the same paging,
filtering, expression and editing tests against the fake and (under
`QGIS_SDK_NATIVE_SERVICES=1`) the native adapter;
`tests/services/test_features_native.py` adds the three-encoding round trip and
a commit a second reader sees; `tests/test_bridge_features.py` drives the eleven
host operations, the page ceiling, the view-scoped session refusal and grant
refusals over fakes. In this workspace the native leg was written but not run
(no PyQGIS): it runs in the QGIS CI job.

**AC4/AC5** are answered in
[decision-72](../decisions/decision-72%20-%20Keep-editing-explicit-rather-than-a-context-manager-and-page-features-rather-than-iterate-them.md)
and in doc-12 ("Why there is no `with` statement, and no `iter_features()`"):
no context manager beside the explicit session, no `iter_features()` generator,
and no part/vertex iterator - `Geometry` carries counts and the encoded payload,
and part/vertex accessors are an additive later change.
