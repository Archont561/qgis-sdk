---
id: TASK-3
title: Render schema-driven native UI and dispatch Python handlers
status: Done
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-24 17:57'
labels: []
milestone: m-1
dependencies:
  - TASK-24
  - TASK-25
priority: medium
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Use the shared plugin description for common native Qt/QGIS actions and forms while leaving behavior in normal Python methods. Preserve an escape hatch for conventional PyQt code.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A declared action and form can be rendered and dispatch validated values to a Python handler.
- [x] #2 Signal/event binding does not serialize Python callables into the description.
- [x] #3 Qt behavior is tested in the appropriate Qt/QGIS test layer.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Closed on 2026-10-24 with CI evidence, because this machine cannot host Qt: PyQt6 wheels install from PyPI and then die on libGL.so.1, and no apt/conda channel is reachable, so the native half could only ever skip here.

What runs now: the pure rules are pinned by test_ui.py (26 tests, ui.py 100 percent) and the Qt/QGIS half by test_ui_native.py, which the checks job runs offscreen in the pixi default environment (QGIS 4.2.3). It genuinely executes there - run 40118398225 passed with no skip warning - after three fixes that only a real host could expose: the module now adds share/qgis/python to sys.path the way tests/services/conftest.py does, the fixture builds a headless QgsApplication because the layer and CRS pickers read a project, and the fixture ids use demo.plain instead of demo:plain, which the declaration validator refuses (that one made the module unrunnable anywhere, not just here).

Criterion by criterion: #1 rendering and validated dispatch are covered by both suites, now including the CI run above; #2 the wire still carries the handler name and the new test asserts the rendered description survives a JSON round trip, so schema_version stays 1; #3 the Qt behaviour lives in its own module, skipped with the ImportError text when the host has no usable Qt, and the CI step warns rather than passing silently when it skips.

Residual, not a criterion: nobody has looked at the dialog on a screen. The rendering is proven by widget assertions under QT_QPA_PLATFORM=offscreen, which is real Qt but not a visual review. Verify locally with: pixi run -e default python -m pytest -c packages/qgis-sdk-python/pyproject.toml packages/qgis-sdk-python/tests/test_ui_native.py -q -rs (pytest 9 exits 5 when the module skips itself; the -rs line says why).
<!-- SECTION:NOTES:END -->
