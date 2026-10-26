---
id: TASK-79
title: >-
  Add UI snapshots: structured tree plus screenshot of the plugin's surfaces,
  dev.ui agent tools and the ui_snapshot fixture
status: To Do
assignee: []
created_date: '2026-10-26T10:01:00Z'
updated_date: '2026-10-26T11:01:00Z'
labels: []
milestone: m-7
dependencies:
  - TASK-75
  - TASK-68
  - TASK-96
type: enhancement
ordinal: 79000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-51. qgis_sdk.ui.snapshot: JSON (canonical, diffable) + PNG of one or every surface the runtime opened, taken on the GUI thread: class-to-role table for Qt and QGIS widgets, per-role value, label association, state, geometry, declared-field link, UI001 finding for widgets without objectName; QWidget.grab() screenshot with DPR; only the plugin's own surfaces. dev.ui.list/open/snapshot/act/diff registered in the dev.* namespace (act is developer mode only; user mode may expose snapshot behind its own grant). ui_snapshot fixture with approve() into tests/__snapshots__/, qgis-sdk ui snapshot <action> CLI, --format yaml in the tools only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A Form snapshot lists every declared field with stable ids, role, value, label and declared link, with a semantic node per catalogue component in front of the Qt role, is byte-identical across two captures, and a custom surface with an unnamed widget yields UI001 (qgis native tests, offscreen).
- [ ] #2 dev.ui.act fills a form and presses Run through QTest and the action runs with the typed values; a re-snapshot shows the new state; act is absent from a user-mode tools list (devtools harness, scripted MCP client).
- [ ] #3 ui_snapshot(...).approve() writes JSON and PNG, a structural change fails with a readable diff, a pixel-only change does not; the snapshot never includes widgets outside the plugin's scope (native test with a second plugin loaded); doc-12 documents the format and the tools.
<!-- AC:END -->
