---
id: TASK-154
title: Explore plugin-owned registration of QGIS objects the SDK does not model
status: To Do
assignee: []
created_date: '2026-11-06 10:05'
updated_date: '2026-11-06 10:05'
labels: []
references:
  - backlog/docs/plans/doc-31 - PyQGIS-corpus-coverage-review.md
  - backlog/docs/plans/doc-22 - Service-coverage-map.md
  - packages/qgis-sdk-runtime/src/qgis_sdk/core/scope.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/declarations/_tools.py
  - backlog/tasks/task-128 - Explore-owned-custom-QGIS-expression-function-declarations.md
  - backlog/tasks/task-129 - Explore-owned-QGIS-layout-and-other-validity-check-declarations.md
priority: medium
type: spike
ordinal: 154000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Several capabilities have the same shape and none of them exist: a layer-tree indicator, a layer-property page, a custom map-canvas item, a custom renderer or symbol layer, a Python expression function (TASK-128), a validity check (TASK-129). Each is "subclass a Qt/QGIS class, then register it and make sure it is unregistered on unload". The SDK models none of them, so the only way to write one is raw PyQGIS inside a plugin whose lifecycle the runtime owns - and nothing guarantees the registration is cleaned up when the plugin is removed or reloaded.

This spike designs the *one* ownership model first (declare, register when the scope opens, roll back a failed registration, unregister exactly what this plugin registered when the scope closes, refuse a collision instead of replacing a stranger's object) and then proves it with one cheap object kind. TASK-128 and TASK-129 are waiting on exactly this model; that is the reason to do it as one spike rather than three.

Proposal only: no milestone, no release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Specify the registration model once - declaration, register, rollback on failure, unregister on unload, collision with an existing object of the same name, and repeated load/unload cycles - and show how TASK-128 and TASK-129 reuse it without a second mechanism.
- [ ] #2 Pick and justify one object kind to prove the model end to end; the cheapest is a layer-tree indicator, because it needs no project file and its absence is observable.
- [ ] #3 Decide how author code may subclass Qt at all without breaking `QGIS001`, the pure target and `UI004`: a native-module declaration, a separate module the check exempts, or a bridge object the SDK builds from a description that carries no Qt.
- [ ] #4 Decide whether a registration that no scope owns is a `.check` finding, a runtime refusal by name, or both - and what the message says.
- [ ] #5 Define the fake (a registry the tests can inspect) and the contract tests, plus the native qualification that a real `iface` is needed for.
- [ ] #6 Record the recommendation, the decision it needs, and the blockers; name what stays permanently out of scope because it would hand out unrestricted Qt objects (decision-9, decision-23).
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read for this proposal: `packages/qgis-sdk-runtime/src/qgis_sdk/core/scope.py` (scope, `quiesce`, owned registrations), `declarations/_tools.py` (the one existing native registration path), `check/ui.py` (`UI004` is the precedent for "declared native is exempt from `QGIS001`"). `QgsLayerTreeRegistryBridge`, `QgsMapLayerConfigWidget` and `registerMapLayerConfigWidgetFactory` do not appear in the tree.

The model must survive the case this repository already exercises: a reload that replaces a revision while work is in flight, which `quiesce()` currently refuses rather than truncating.
<!-- SECTION:NOTES:END -->
