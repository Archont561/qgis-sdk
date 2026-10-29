---
id: TASK-140
title: Spike a FastAPI-style plugin application and action groups for 0.8.0
status: Done
assignee: []
created_date: '2026-10-28 17:39'
updated_date: '2026-10-29 09:03'
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
  - >-
    backlog/docs/plans/doc-30 -
    TASK-140-plugin-application-and-action-groups-spike.md
  - >-
    backlog/decisions/decision-68 -
    Explore-additive-plugin-applications-with-explicit-action-groups.md
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
- [x] #1 Compare the existing class form and a namespace-only alias and a plugin application object with registered functions; present complete small and multi-module examples including typed action inputs and explicit group inclusion and test ergonomics.
- [x] #2 Prototype the app and action/group registration with explicit plugin ownership and deterministic IDs and duplicate detection; define import and include behavior and reject implicit module scanning or a global current-plugin registry. Verify two plugin applications remain isolated.
- [x] #3 Design typed PluginContext injection and test overrides without exposing injected host dependencies in action request schemas; preserve handler identity where feasible and define typing and dependency-injection limits. Coordinate with TASK-122 without adding a FastAPI or Pydantic runtime dependency.
- [x] #4 Demonstrate how surfaces and stacked toolbar/menu/shortcut bindings and streams and providers and lifecycle ownership compose with the new form; preserve action authorization and scopes and native QGIS thread constraints. Coordinate future named jobs with TASK-115/116 without moving the agreed 0.9.0 job refactor into 0.8.0.
- [x] #5 Evaluate shared describe(target) and target.describe() support including action bindings and wire metadata; prove equivalent public plugin descriptions and bridge schemas for equivalent class and app examples or document any contract changes and their compatibility consequences. Coordinate diagnostic JSON with TASK-137.
- [x] #6 Assess module:attribute project discovery and CLI check/test/dev/build and scaffold and web generation plus plugin startup/unload/reload and coexistence; identify changes and compatibility risks for existing class-based projects and generated clients.
- [x] #7 Record a recommendation and decision with prototype evidence and trade-offs and migration and release impact; if viable identify implementation slices and qualification gates for 0.8.0 including the TASK-78 bridge/version assumptions. If not viable state blockers and propose an alternative without claiming delivery.
- [x] #8 Exercise representative pure tests and fake contexts plus a realistic native-QGIS qualification plan; cover invalid imports and collisions and multi-plugin isolation and generated schema parity. Document trusted-code import/annotation evaluation and do not claim unproven native behavior.
- [x] #9 Coordinate with TASK-128 on a possible app.expression_function declaration and SDK-owned read-only ExpressionContext injection; assess ownership and introspection without treating expression registration as implemented or moving its release target.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Compare existing authoring alternatives and inspect runtime/tooling seams; build a non-shipping explicit-ownership prototype with public-seam tests and schema/dispatch evidence; document lifecycle, injection, tooling, expression and release risks with a scoped recommendation and qualification plan.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Completed a non-shipping authoring spike; decision-68 is proposed, not accepted. Doc-30 records alternatives, examples, context injection, tooling, lifecycle, expression coordination and 0.8.0 qualification gates. The script lowers explicit action and stream groups to SDK plugin classes; representative class and app descriptions and generated schema text match. Follow-up experiments add an isolated module:app resolver and SDK describer registration for the app and original handlers, including action binding and wire metadata; actual SDK host and tools still reject an app object directly. Linux x86-64 QGIS 4.2.3, Qt 6.11.2, Python 3.14.8: an offscreen QGIS host test with a fake Desktop interface exercised two prototype apps, real Qt actions and dialogs, real empty-provider registration, duplicate-provider startup rollback, independent cleanup and host restart. This is not an installed plugin or real Desktop/source-edit reload, provider-algorithm execution, WebEngine or Windows/macOS qualification. Original handler UI wire execution remains unproven. Focused SDK, native and spike tests: 205 passed; whole-tree Ruff, Biome, docs build/link check and backlog doctor passed. The recommendation does not authorize implementation or release; worker-first jobs remain 0.9.0 and TASK-128 retains expression-context ownership. Task remains In Progress until review and merge.

Follow-up full workspace coverage after placing the native test alongside the other native tests: six tasks succeeded; Python 1950 passed, 62 skipped, 96.99%. An initial run failed two bare-interpreter tests because the new test initialized QGIS earlier in the same process; correcting test placement resolved those failures. Docs link check: 6954 internal links, zero broken.

Real Desktop follow-up: actual QGIS 4.2.3 executable and qgis.utils.iface, Qt 6.11.2/Python 3.14.8 on Linux, clean temporary profile, offscreen. QGIS plugin discovery and manager loaded two prototype directory fixtures; real provider registration, GUI-thread actions/dialogs, independent unload and final cleanup passed. Editing one action from double to triple and QGIS unload/reload produced a fresh module and changed result 42 to 63. Four opt-in harness tests passed. No visible display or ZIP; production SDK module:app remains unsupported, and UI-wire execution, provider algorithms, WebEngine and cross-platform qualification remain open.

Post-Desktop-harness workspace coverage: 6/6 tasks passed, Python 1953 passed, 63 skipped, 96.99%; opt-in real Desktop tests passed separately (4/4). Whole-tree Ruff/format, docs build and link check (7040 links, 0 broken), Backlog doctor and diff check passed.

The spike and subsequent approved QgisSdkPlugin migration landed in PR #130 at f70c67c67c3046927cfb183b383e51fd69ac3f97 with passing PR CI. TASK-141 retains the separate supported-platform and packaging qualification gate.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The application-authoring spike was completed and informed the approved production migration in PR #130.
<!-- SECTION:FINAL_SUMMARY:END -->
