---
id: TASK-128
title: Explore owned custom QGIS expression function declarations
status: To Do
assignee: []
created_date: '2026-10-28 15:58'
updated_date: '2026-10-28 17:55'
labels: []
dependencies: []
references:
  - packages/qgis-sdk-runtime/src/qgis_sdk/core/scope.py
  - packages/qgis-sdk-runtime/src/qgis_sdk/providers.py
priority: medium
type: spike
ordinal: 128000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explore an SDK declaration for custom QGIS Expression Builder functions and typed host-context injection without requiring plugin authors to import PyQGIS. The owner wants an SDK-owned ExpressionContext with read-only typed access and fake-backed tests; app.expression_function is an illustrative possible syntax from TASK-140 and not an implemented API. TASK-86 covers evaluating and validating expressions rather than author-defined registration. Determine an additive design and qualification before committing to a release; do not promise implementation or assign a release in this spike.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Specify typed authoring, metadata and help, safe native registration, name collisions, thread/context expectations and duplicate versions across vendored plugins; preserve access to native PyQGIS.
- [ ] #2 Specify ownership, unload/reload cleanup, registration failures and pure fake/native contract tests; decide whether or how describe and bridge permissions apply.
- [ ] #3 Compare class-based plugin declarations and the proposed app.expression_function form from TASK-140; specify typed arguments and results and function group and name and help metadata without requiring PyQGIS imports in author code.
- [ ] #4 Design SDK-owned typed ExpressionContext and feature/variable/geometry access using restricted read-only capabilities rather than unrestricted mutable PluginContext; specify absent features and variables and nulls and type mismatches and feature lifetime without leaking QGIS objects.
- [ ] #5 Inject the context from the host for each expression evaluation while excluding it from the expression argument list and any public input schema or generated client; keep expression parameters explicit and specify value conversion and error reporting.
- [ ] #6 Specify QGIS adapter and pure fake-context behavior and direct handler test ergonomics; prototype or test representative feature and variable reads and null and invalid inputs with pure and native-QGIS contract tests.
- [ ] #7 Define referenced columns and geometry and null-handling metadata with safe defaults and correct QGIS expression behavior; avoid per-feature costly operations and avoid exposing side-effectful services without proven host safety.
- [ ] #8 Verify expression evaluation threads and reentrancy and object lifetime on supported QGIS hosts; document constraints and fail or limit capabilities where thread safety is unproven. Do not assume evaluation always occurs on the GUI thread.
- [ ] #9 Register without replacing existing shared QGIS functions; define name collision handling and rollback and protect against unregistering a different owner on unload or reload. Test collisions and two plugins and repeated or failed startup and ownership cleanup.
- [ ] #10 Coordinate the API and typed injection with TASK-140 and features/expression services with TASK-86 while keeping worker jobs in their existing milestone; explicitly decide whether descriptions or bridge access include these functions and require no FastAPI or Pydantic dependency.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
QGIS 4.2.3 headless probe: a qgsfunction created with register=False registered through QgsExpression.registerFunction; fieldtools_double(21) evaluated to 42 and the same object was found in Functions() before successful unregister. This is a narrow probe, not evidence of cross-version identity, collision safety or thread behavior.
<!-- SECTION:NOTES:END -->
