---
id: TASK-25.4
title: Apply packaged QML to compatible outputs
status: Done
assignee: []
created_date: '2026-10-24 14:28'
updated_date: '2026-10-24 15:14'
labels: []
milestone: m-1
dependencies:
  - TASK-25.2
references:
  - >-
    backlog/decisions/decision-16 -
    Separate-reusable-layer-styles-from-UI-themes.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
  - backlog/docs/plans/doc-9 - V2-sprint-train-and-0.2.0-dependency-order.md
parent_task_id: TASK-25
priority: medium
type: feature
ordinal: 25400
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sprint 1, slice 4 (TASK-25). Apply a reviewed packaged QML style resource to a compatible output through the layer service, and refuse incompatible targets explicitly.

Scope boundary from decision-16: this is layer styling, not UI theming. No global stylesheet or palette mutation, and no promise of CSS/QSS equivalence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A reviewed packaged QML resource applies to a compatible output through the layer service, with the style resource shipped with the package rather than read from an ambient path.
- [x] #2 A layer/geometry/field mismatch is refused with a structured QgisSdk error naming the incompatibility, never a partial or silent application.
- [x] #3 No global stylesheet or application palette is mutated, and native theme inheritance is untouched, proven by a test rather than by review.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 implemented (TDD).

Scope landed: a new pure `qgis_sdk.resources` package holding the reviewed catalog (`STYLE_CATALOG`), `require_style`/`style_path` resolution from the installed package, and two packaged QML resources (point and line symbols). `StyleSpec` plus its one compatibility rule live in `qgis_sdk.models.styles`, so the fake and the PyQGIS adapter make the identical decision instead of each implementing its own. `NativeStyles` validates first, then loads the packaged QML with `loadNamedStyle`. Two new prefixed errors: `QgisSdkStyleNotFoundError` (unknown catalog identifier) and `QgisSdkPackagedResourceError` (packaged file missing or rejected by QGIS - a packaging defect, not a caller mistake).

AC #1: the style is requested by catalog identifier and resolved by `style_path` from `qgis_sdk/resources/styles`, never from an ambient path; the test asserts the resolved file is under the package root. Proven at artifact level too: `python -m build --no-isolation` produced `qgis_sdk-0.1.1-py3-none-any.whl` containing `qgis_sdk/resources/styles/reference-line-output.qml` and `reference-point-output.qml`, so the resource ships rather than living only in the source tree.

AC #2: both refusal classes are structured and named. Unknown identifier raises `QgisSdkStyleNotFoundError`. A geometry mismatch, a missing required field, or both at once raise `QgisSdkStyleIncompatibleError` with `reasons`, `layer_id` and `style`, listing every mismatch rather than the first. Validation runs before any QML is loaded, so nothing partial is applied: the fake proves `applied() == ()` after a refusal and the native theme test proves the layer's renderer signature is unchanged.

AC #3: proven, not reviewed. `tests/services/test_native_styles_theme.py` snapshots the application stylesheet and six palette roles (Window, WindowText, Base, Text, Button, Highlight) before and after a successful application and asserts equality; the real-host harness repeats that check and reports `theme_unchanged: true`. Nothing in this slice reads or writes application styling.

Evidence from the real host (QGIS 4.2.3-Belém do Pará, Qt 6.11.2, CPython 3.14.8): `scripts/native_services_smoke.py` reports `passed: true` with `style_applied`, `style_incompatible_refused` and `theme_unchanged` true alongside the earlier layer/project/settings/notification stages.

Coverage: the new pure modules are at 100% (`models/styles.py` 19 statements, `resources/__init__.py` 19). Driving the packaging-defect path needed a real test rather than a pragma, so `test_resources.py` monkeypatches `STYLE_DIRECTORY` to an empty directory and asserts `QgisSdkPackagedResourceError` - that closed the last 4 uncovered statements in `models/errors.py` and `resources/__init__.py`.

Validation: pure suite 466 passed / 10 skipped (the three native-only theme tests skip); with `QGIS_SDK_NATIVE_SERVICES=1 QGIS_SDK_NATIVE_SERVICES_SMOKE=1` the package suite is 478 passed / 6 skipped; coverage 100.00% (1118 statements); ruff check and format clean; wheel and sdist build with the QML included; `backlog doctor` clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Reviewed packaged QML applies through the layer service with catalog-driven compatibility checks, refuses every mismatch as a structured error before touching the layer, and the application theme is proven unchanged by test and by the real-host harness.
<!-- SECTION:FINAL_SUMMARY:END -->
