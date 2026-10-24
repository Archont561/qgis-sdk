---
id: TASK-25.1
title: 'Curated layer, project, settings and style contracts with in-memory fakes'
status: Done
assignee: []
created_date: '2026-10-24 14:27'
updated_date: '2026-10-24 14:43'
labels: []
milestone: m-1
dependencies: []
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
ordinal: 25100
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 1 (TASK-25). Add only the QGIS-free capabilities the accepted reference workflow needs (decision-19), as Protocols in `qgis_sdk.services`, plus in-memory fakes that satisfy the same contract tests the native adapters will.

Deliberately not a service manager: no mirror of QgsVectorLayer or QgsProject, and no capability without a caller. Every protocol added here is consumed by slice 2, 3 or 4, or by TASK-14/TASK-3.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Only capabilities the accepted reference workflow needs are added; no general PyQGIS mirror and no capability without a caller.
- [x] #2 The new contracts and fakes import and run with qgis, PyQt and pydantic blocked, and tests/test_pure_imports.py covers every new module.
- [x] #3 The in-memory fakes pass the same contract tests the native adapter will be held to, so fake/native parity is a test property rather than a review claim.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 implemented (TDD; environment restored with scripts/restore.sh, frozen Bun install, no dependency or lockfile change).

Scope landed: four QGIS-free contracts in `qgis_sdk.services` (`Layers` open/list/layer/selection, `Project` layer_ids/add_layer, `Settings` get/set, `Styles` apply_style) plus `VectorLayerInfo` in `qgis_sdk.models` and two prefixed errors (`QgisSdkLayerNotFoundError`, `QgisSdkStyleIncompatibleError`). In-memory doubles live in the new `qgis_sdk.testing` package. No PyQGIS mirror: nothing edits geometry or attributes, and `Project.add_layer` is a separate explicit step so a caller adds an output only after success (decision-19). `VectorLayerInfo` carries `crs` and `field_names` because TASK-25.4 validates style compatibility against them and TASK-14 needs the CRS for projected/units checks.

AC #1: 9 methods across 4 contracts; every one has a caller in 25.2/25.3/25.4 or in TASK-3/TASK-14. Selection is read-only by design (setting it is a host action, so `select` is fake-only setup, not contract).

AC #2: `tests/test_pure_imports.py` now ranks `testing` outermost (3), imports `qgis_sdk.testing` in the subprocess run that blocks qgis/PyQt/pydantic, and adds a dedicated guard that no shipping module imports the doubles. Both guards were verified by mutation: appending `from qgis_sdk.testing import FakeLayers` to `models/__init__.py` failed two tests (`[models]` and the new guard), then the violation was reverted.

AC #3: `tests/services/conftest.py` holds one contract suite parameterised over `BACKENDS`; the fake is the only registered entry today and the native adapter joins by adding a factory, so the same 23 tests will hold it without being rewritten. Fake-only observability (recorded notifications, applied styles) is tested separately in `test_fakes.py`, not in the contract suite.

Validation: root suite 433 passed / 6 skipped; coverage 100.00% (1047 statements, 0 missed, services and testing at 100%); ruff check and format clean; `backlog doctor` clean. Red evidence captured before implementation: conftest import failed with `ImportError: cannot import name 'Layers' from 'qgis_sdk.services'`.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Curated layer/project/settings/style contracts and in-memory fakes landed with a single backend-parameterised contract suite; 433 tests pass at 100% coverage.
<!-- SECTION:FINAL_SUMMARY:END -->
