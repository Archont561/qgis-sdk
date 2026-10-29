---
id: TASK-79
title: >-
  Add UI snapshots: structured tree plus screenshot of the plugin's surfaces,
  dev.ui agent tools and the ui_snapshot fixture
status: To Do
assignee: []
created_date: '2026-10-26T10:01:00Z'
updated_date: '2026-10-29T16:20:00Z'
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

2026-10-29 progress: slices S1 and S2 landed (82ec11c, b7cac82).

S1 (tree) - qgis_sdk/ui/snapshot.py gained surface_snapshot(...) and canonical_json(...): semantic role per node in front of the Qt class, per-role value, label from QLabel.buddy(), enabled/visible/focus, geometry accumulated through parentWidget()/pos() into surface coordinates, declared link for form/<field> and buttons/<name>, and UI001 findings for unnamed actionable widgets (positional id). Pure tests: packages/qgis-sdk-python/tests/test_ui_surface_snapshot.py (6).

S1 (PNG) - qgis_sdk/adapters/snapshot.py captures with QWidget.grab(), encodes PNG through QBuffer, records devicePixelRatio and stores sha256 in the tree as screenshot. Kept out of qgis_sdk.ui on purpose: test_pure_imports forbids Qt in the pure layer and caught the first placement.

S2 (scope) - SurfaceHost.snapshot(surface_id=None, screenshot=True) captures the dialogs it showed plus the docks it left visible, refuses an unknown id, and never reaches outside its own registry. Native tests: packages/qgis-sdk-python/tests/test_ui_surface_snapshot_native.py (7, offscreen), including digest-equals-PNG, byte-identical repeat captures, dock visibility filtering and SurfaceCapture.write(). Full suite: 2041 passed / 58 skipped / 7 deselected; ruff, format, alint clean.

S3 (tools, CLI) - qgis-sdk ui list/open/snapshot/act/diff, each one writing a request into .qgis-sdk/ui/ and running qgis_sdk_tools.devtools.ui_probe in a QGIS interpreter (the CLI process never touches a widget). ui_probe gained CaptureRequest.open_only and CaptureReport.opened, so open reports the window it produced without writing a capture; act reports the value the widget holds after each step. Steps are NODE:VERB[:VALUE] on the command line and refused with the verb list before QGIS starts. ui_diff gained nothing this slice; qgis_sdk_tools.ui_yaml.to_yaml renders a capture as YAML for reading (--format yaml in the tools only - files on disk stay canonical JSON, and the runtime has no YAML). MCP exposes qgis_sdk_ui_list/open/snapshot/act/diff, with DEVELOPER_ONLY = {ui_act} and tool_names(developer=...) as the gate: the reading tools survive without developer tooling, ui act does not.

S3 (gating, AC 2) - decision-49 was superseded and TASK-76 was withdrawn, so there is no agent user mode to hide act in; the list a user's install does offer is the plugin HTTP description (GET /plugin), which can only name declared actions and streams and has no surface tool. So the gate is now two facts, both tested: test_mcp_cli::test_act_is_developer_only_in_the_tool_list (scripted MCP client vocabulary) and test_pure_imports::test_the_runtime_tree_never_reaches_for_synthetic_input (the vendored runtime never reaches QtTest). The probe's first QTest click aborted the process (qt_assert) because the test's RunButton handed the action None instead of form values - a plugin bug the probe reported correctly, not a probe bug.

Tests: test_ui_cli.py (17, FakeCliRuntime + a fake probe process), test_ui_yaml.py (6, yaml.safe_load round-trip as the oracle), test_ui_probe_native.py (8, real offscreen QgsApplication, plugin started through its generated classFactory), test_mcp_cli.py (6 including the scripted stdio client), test_pure_imports.py (25). apps/docs/src/content/docs/guides/cli-mcp.md lists the five surface tools and says act is developer-only.

Remaining: S4 ui_snapshot fixture with approve()/structural diff, the two-plugin isolation test and the doc-12 section (AC 3).
<!-- SECTION:NOTES:END -->
