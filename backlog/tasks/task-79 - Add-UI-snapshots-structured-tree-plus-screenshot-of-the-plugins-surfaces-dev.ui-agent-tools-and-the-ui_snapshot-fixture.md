---
id: TASK-79
title: >-
  Add UI snapshots: structured tree plus screenshot of the plugin's surfaces,
  dev.ui agent tools and the ui_snapshot fixture
status: To Do
assignee: []
created_date: '2026-10-26T10:01:00Z'
updated_date: '2026-10-29T14:40:00Z'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-29 slice plan (survey before implementation).

Existing that this task builds on, verified in the tree:
- qgis_sdk/ui/snapshot.py already exists but is a different, smaller thing: ui_snapshot(target)/snapshot_names walk a catalogue Component or a Qt widget and return {type, objectName, text, children}. It is consumed by test_ui_catalogue.py, test_ui_declarative.py, test_scaffold_ui.py and test_ui_catalogue_native.py. It has no role table, no per-role value, label association, state, geometry, declared link, findings or PNG, and no canonical JSON.
- Stable ids already exist: TASK-68 AC 4 gave generated widgets objectName form/<field> and buttons/<name>, and check/ui.py raises UI001 for an interactive widget without one.
- The surfaces a plugin opened are already tracked: SurfaceHost.dialogs(), SurfaceHost.docks(), SurfaceHost.open(), SurfaceHost.close_all() in qgis_sdk/adapters/surfaces.py. That is the decision-51 point 6 boundary - no QGIS main-window walk.
- There is no dev.ui.* namespace, no qgis-sdk ui command, no tests/__snapshots__ fixture and no approve()/diff yet.

Decisions taken for the implementation:
- Extend qgis_sdk/ui/snapshot.py rather than add a second module named snapshot: add surface_snapshot(...) (Qt or duck-typed surface -> decision-51 payload: surface, kind, title, size, palette, scale, screenshot hash, nodes, findings) and canonical_json(...) (sorted keys, no spaces, float rounding, trailing newline). ui_snapshot stays as-is so the four existing consumers do not move.
- The pytest fixture keeps the decision-51 name ui_snapshot(surface); fixtures live in a separate namespace from the module function, so both names coexist.
- Snapshots come from SurfaceHost's own registry only: host.snapshot(surface_id|None) refuses an unknown id and never reaches another plugin's surfaces.

Slices (each its own commit and verification):
S1 core - role table with the semantic node in front of the Qt role, per-role value, label via QLabel.buddy() and QFormLayout rows, enabled/visible/focus, geometry mapped to surface coordinates, declared link from objectName, UI001 findings for unnamed interactive widgets, byte-identical repeat captures, QWidget.grab() PNG with device pixel ratio (offscreen). Covers AC 1 and the JSON/PNG half of AC 3.
S2 host - SurfaceHost.snapshot over the surfaces it opened, unknown-id refusal, isolation test with a second plugin loaded. Covers the scope half of AC 3.
S3 agent tools and CLI - dev.ui.list/open/snapshot/act/diff with act through QTest, developer mode only (absent from a user-mode tools list), qgis-sdk ui snapshot <action> writing .qgis-sdk/ui/, --format yaml in the tools only. Covers AC 2 and the CLI clause of AC 3.
S4 fixture and docs - ui_snapshot fixture with approve() into tests/__snapshots__/, structural change fails with a readable diff, pixel-only change does not, doc-12 section on format and tools. Completes AC 3.

Environment note for the native slices: pixi run sets PYTHONPATH from [activation.env], which overrides qgis-activate.sh, so qgis.core imports only when share/qgis/python and share/qgis/python/plugins are appended to PYTHONPATH (QT_QPA_PLATFORM=offscreen). Verified: qgis 4.2.3 imports that way.
<!-- SECTION:NOTES:END -->
