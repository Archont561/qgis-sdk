---
id: TASK-140
title: Spike a FastAPI-style plugin application and action groups for 0.8.0
status: To Do
assignee: []
created_date: '2026-10-28 17:39'
updated_date: '2026-10-28 17:55'
labels: []
milestone: m-7
dependencies: []
references:
  - packages/qgis-sdk-runtime/src/qgis_sdk/declarations/_plugin.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/providers.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/declarations/_describe.py
  - packages/qgis-sdk-tools/src/qgis_sdk_tools/_commands/_bridge.py
  - >-
    backlog/decisions/decision-9 -
    Declare-allowlisted-typed-bridge-endpoints-with-runtime-owned-routers.md
priority: high
type: spike
ordinal: 140000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner wants to explore a FastAPI-like plugin application object for the next Python release (0.8.0): for example app = Plugin(...) and @app.action functions, with explicit composable action groups for larger plugins. The goal is a decision and evidence that can support delivering an approved authoring style in 0.8.0, not an assertion that it is implemented or a release authorization. Compare it with the current @plugin class and @action methods and the lighter @plugin.action namespace alias. Prefer an additive path initially; preserve existing class-based plugins unless a separate breaking change is explicitly approved. This is not FastAPI HTTP routing and must not require FastAPI or Pydantic.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compare the existing class form and a namespace-only alias and a plugin application object with registered functions; present complete small and multi-module examples including typed action inputs and explicit group inclusion and test ergonomics.
- [ ] #2 Prototype the app and action/group registration with explicit plugin ownership and deterministic IDs and duplicate detection; define import and include behavior and reject implicit module scanning or a global current-plugin registry. Verify two plugin applications remain isolated.
- [ ] #3 Design typed PluginContext injection and test overrides without exposing injected host dependencies in action request schemas; preserve handler identity where feasible and define typing and dependency-injection limits. Coordinate with TASK-122 without adding a FastAPI or Pydantic runtime dependency.
- [ ] #4 Demonstrate how surfaces and stacked toolbar/menu/shortcut bindings and streams and providers and lifecycle ownership compose with the new form; preserve action authorization and scopes and native QGIS thread constraints. Coordinate future named jobs with TASK-115/116 without moving the agreed 0.9.0 job refactor into 0.8.0.
- [ ] #5 Evaluate shared describe(target) and target.describe() support including action bindings and wire metadata; prove equivalent public plugin descriptions and bridge schemas for equivalent class and app examples or document any contract changes and their compatibility consequences. Coordinate diagnostic JSON with TASK-137.
- [ ] #6 Assess module:attribute project discovery and CLI check/test/dev/build and scaffold and web generation plus plugin startup/unload/reload and coexistence; identify changes and compatibility risks for existing class-based projects and generated clients.
- [ ] #7 Record a recommendation and decision with prototype evidence and trade-offs and migration and release impact; if viable identify implementation slices and qualification gates for 0.8.0 including the TASK-78 bridge/version assumptions. If not viable state blockers and propose an alternative without claiming delivery.
- [ ] #8 Exercise representative pure tests and fake contexts plus a realistic native-QGIS qualification plan; cover invalid imports and collisions and multi-plugin isolation and generated schema parity. Document trusted-code import/annotation evaluation and do not claim unproven native behavior.
- [ ] #9 Coordinate with TASK-128 on a possible app.expression_function declaration and SDK-owned read-only ExpressionContext injection; assess ownership and introspection without treating expression registration as implemented or moving its release target.
<!-- AC:END -->
