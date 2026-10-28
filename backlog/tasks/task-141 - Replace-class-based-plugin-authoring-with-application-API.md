---
id: TASK-141
title: Replace class-based plugin authoring with application API
status: In Progress
assignee: []
created_date: '2026-10-28 20:34'
updated_date: '2026-10-28 22:33'
labels: []
dependencies:
  - TASK-140
priority: high
type: feature
ordinal: 141000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner requested a breaking migration from class-based authoring to a single instantiated QgisSdkPlugin API; private runtime class lowering may remain. Plugins can compose declarations, register surfaces via decorator, and default metadata from the declaring module. This is implementation, not the TASK-140 spike.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Public authoring uses QgisSdkPlugin with typed context injection, unified descriptions, scoped runtime isolation, surface decorators, derived metadata and atomic plugin composition; remove the old public class API.
- [x] #2 Desktop host, generated build/dev artifacts, CLI, checks and scaffold resolve module:app, including providers, surfaces, UI bindings and reload.
- [x] #3 Migrate all current examples, active documentation, tests and scripts; document the breaking migration and preserve historical release notes.
- [ ] #4 Qualify real QGIS Desktop, package ZIP installation, full workspace coverage and supported platforms before release.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The production public authoring API is PluginApp and ActionGroup, with explicit composition, typed PluginContext injection, app/handler descriptions and per-runtime isolation. Public plugin/action/stream/describe_plugin and class-only PluginFactory/declared_providers APIs were removed. PluginRuntime, describe, describe_bindings, DesktopLifecycleAdapter and create_class_factory reject former plugin classes; class lowering and regression tests remain private. FakeUi accepts an application. Historical release notes and private lowering regression fixtures are retained.

Desktop host, CLI/generation, build/dev artifacts, examples, guides, scaffold options and qualification scripts use module:app. The checker recognises directly imported local groups without executing project code; it cannot infer dynamic or re-exported group aliases. Scaffold schema parity covers web + Processing + native UI. UI wires execute on surface methods; wire metadata on an application action does not implicitly connect it to a surface.

2026-10-28 local evidence: workspace coverage 6/6 tasks; Python 1967 passed, 63 skipped, 96.91%. Real Linux x86-64 QGIS 4.2.3 offscreen Desktop: 42 lifecycle/adapter/ZIP tests passed, plus an updated 4-test app harness proving a wired surface dispatches an action, reload and isolated cleanup. Native Processing provider execution passed 12 tests. QGIS CLI native/Desktop target and dev/reload passed 7 tests. Reference plugin qualification passed 5 tests, including built WebEngine page, native dialog, Processing and ZIP build. Docs build and 7042 links passed, as did Python lint/format and TypeScript typecheck. These do not establish visible-GUI or other-platform/QGIS-version support. Keep AC4 open and do not claim cross-platform release qualification.

Workspace build: the three Python wheels built and passed package checks, but the overall build failed in build:conda because this sandbox cannot fetch conda-forge repodata (TLS handshake EOF). Conda packaging remains unverified here.

Superseding the earlier design notes: the sole public authoring type is QgisSdkPlugin, not PluginApp or ActionGroup. Inclusion snapshots actions, streams, surfaces and providers into one root runtime and rejects child context factories, collisions, duplicate inclusion and cycles. Surface decorators preserve classes; plugin defaults derive from the declaring module. Current workspace coverage: 6/6 tasks, Python 1974 passed, 63 skipped, 96.89%. A composed plugin passed the real offscreen QGIS Desktop plugin manager harness (4 tests) and the QGIS-native provider/UI lifecycle test. AC4 remains open for full supported-platform qualification and Conda packaging.

Final redesigned-API checks: workspace coverage 6/6 tasks, Python 1975 passed and 63 skipped at 96.89%; documentation built with 7042 internal links and no broken links. Real QGIS offscreen: composed-plugin Desktop harness 4 passed, generated scaffold and Desktop adapter 37 passed (plus one separate lifecycle opt-in), native lifecycle harness 5 passed, reference plugin 5 passed, and QGIS-native composition 1 passed. Three updated Python wheels built and passed twine checks. Visible GUI, other platforms and Conda packaging remain unqualified.
<!-- SECTION:NOTES:END -->
