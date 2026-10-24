---
id: TASK-3
title: Render schema-driven native UI and dispatch Python handlers
status: In Progress
assignee: []
created_date: '2026-10-15 23:06'
updated_date: '2026-10-24 17:19'
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
- [ ] #1 A declared action and form can be rendered and dispatch validated values to a Python handler.
- [ ] #2 Signal/event binding does not serialize Python callables into the description.
- [ ] #3 Qt behavior is tested in the appropriate Qt/QGIS test layer.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
First slice landed on arena/048b6e92-qgis-sdk: qgis_sdk/ui.py (schema + Annotated markers -> widget family, strict value coercion) and adapters/qgis/ui.py (NativeForms + DeclaredFormDialog). The wire contract is unchanged - a description still carries the handler *name*, never a callable, so AC #2 holds by construction and the plugin-description schema stays at 1. 25 pure tests; ui.py is at 100% coverage. AC #1 and #3 stay OPEN: the Qt path has not been executed anywhere yet. This sandbox has no PyQt6 or QGIS, so tests/test_ui_native.py skips here and in the QGIS-free CI jobs; run 'pixi run -e qgis python -m pytest packages/qgis-sdk/tests/test_ui_native.py' and confirm the dialog on a real host before closing.
<!-- SECTION:NOTES:END -->
