---
id: TASK-25.2
title: Native layer and project adapter with explicit ownership
status: Done
assignee: []
created_date: '2026-10-24 14:28'
updated_date: '2026-10-24 14:57'
labels: []
milestone: m-1
dependencies:
  - TASK-25.1
references:
  - >-
    backlog/decisions/decision-6 -
    Separate-models-services-core-and-runtime-adapters.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
parent_task_id: TASK-25
priority: medium
type: feature
ordinal: 25200
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 2 (TASK-25). PyQGIS-backed implementations of the layer and project contracts from slice 1: layer lifetime, selection reads, scoped resource operations and output ownership.

Ownership rules come from decision-19: the source is never mutated, a produced output is a new object, and project addition happens only after success. Every scoped operation closes through the existing `ResourceScope` rather than a new registry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Layer lifetime, selection reads and output ownership are explicit API semantics; no wrapper reproduces QgsVectorLayer and no service hides who owns an output.
- [x] #2 Scoped resource operations close through the existing ResourceScope and are idempotent on repeat, including after a failed operation.
- [x] #3 Fake and native adapters pass the same contract tests, and a real QGIS 4.2.3 host test proves the native path with no fake fallback.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 implemented (TDD; environment restored with scripts/restore.sh, frozen Bun install, no dependency or lockfile change).

Scope landed: `qgis_sdk.adapters.qgis` with `NativeLayers` (OGR open via `QgsVectorLayer`, describe, read selection) and `NativeProject` (`QgsProject` membership, add-once). Both take the owner `ResourceScope`: every operation calls `ensure_open()` first, so work after disposal raises `QgisSdkScopeClosedError` instead of returning a stale handle, and `on_close` clears the adapter's layer references (decision-20). `NativeProject` takes the project as an injectable constructor argument defaulting to `QgsProject.instance()`, so a test can isolate membership. `NativeLayers._qgs_layer` is the documented package-internal handoff that lets the sibling adapter add the very instance it owns; author and bridge code never see it.

AC #1: `VectorLayerInfo` only crosses the boundary; no wrapper reproduces `QgsVectorLayer`, nothing edits geometry or attributes, and `NativeProject.add_layer` never runs on its own (decision-19 keeps project addition explicit and after success).

AC #2: scope semantics are a contract, not an implementation detail - `tests/services/test_scope_contract.py` (7 tests) checks that opening, listing, reading a layer, reading a selection, reading membership and adding to the project are all refused after close, and that a repeated close is safe. The fakes carry the same scope so both backends are held to it.

AC #3: `tests/services/conftest.py` registers a `native` backend behind `QGIS_SDK_NATIVE_SERVICES=1`, so the same 26 contract tests run against fake and native (56 passed). `scripts/native_services_smoke.py` runs on the real host and reports `passed: true` against QGIS 4.2.3-Belém do Pará / Qt 6.11.2 / CPython 3.14.8: layer `points` opened, EPSG:4326, fields (id, value), a selection made through `QgisProject` read back through the contract as (1, 3), membership length 1, scope closed, reads refused, QGIS exited. Its opt-in test is `QGIS_SDK_NATIVE_SERVICES_SMOKE=1`.

Evidence detail worth keeping: GDAL reports the RFC 7946 fixture as EPSG:4326, so the fixture declaration (tests/fixtures/reference/points.geojson) is the single source of truth shared by both backends rather than a per-backend constant.

Coverage: the native adapters import PyQGIS at module scope (decision-14), so the QGIS-free coverage job cannot execute them. `.coveragerc` now omits `qgis_sdk/adapters/qgis/*` with the reason and names both places they are measured; the reported total stayed 100.00% (1061 statements) instead of silently falling to 94.40% for code that job cannot import.

Validation: pure suite 444 passed / 7 skipped; with `QGIS_SDK_NATIVE_SERVICES=1 QGIS_SDK_NATIVE_SERVICES_SMOKE=1` the package suite is 446 passed / 6 skipped; coverage 100.00%; ruff check and format clean; `backlog doctor` clean. Red evidence captured before implementation: the scope contract module errored on the unscoped fakes, and the first native run failed on a wrong fixture path before passing 26/26.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PyQGIS-backed layer and project adapters land behind the same contracts as the fakes; 26 contract tests pass on both backends and the headless host harness reports passed on QGIS 4.2.3.
<!-- SECTION:FINAL_SUMMARY:END -->
