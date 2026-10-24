---
id: TASK-14
title: Implement class based Processing algorithms and safe outputs
status: Done
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 15:41'
labels: []
milestone: m-1
dependencies:
  - TASK-24
  - TASK-25
references:
  - >-
    backlog/decisions/decision-11 -
    Use-one-context-injected-class-per-Processing-algorithm.md
  - >-
    backlog/decisions/decision-19 -
    Prove-a-non-destructive-local-GIS-reference-workflow.md
priority: medium
type: feature
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement class based Processing algorithms and safe outputs. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Inspect one decorated plain class/run entry point and construct fresh execution context per invocation.
- [x] #2 Map typed parameters/results with explicit projected CRS/units and non-destructive output semantics.
- [x] #3 Pure and real Processing tests prove source preservation, cleanup and GUI-side project addition after success.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 completed. The authoring half of decision-11 plus the safe-output half of decision-19, with the gaps written down rather than glossed over.

**Authoring surface.** New pure module `qgis_sdk.algorithms`: `@algorithm` attaches metadata without wrapping the class, `describe_algorithm` inspects it **without constructing it** (a test records constructions during a describe and asserts the list is empty), and `invoke` constructs a **fresh author instance and a fresh `AlgorithmContext`** per call over a child scope it then closes. A test runs the same class twice and asserts distinct instances, distinct contexts and distinct scopes, all closed.

Request and result schemas come from the same `qgis_sdk.declarations` generator that describes plugin actions, so an algorithm's inputs sit inside the one documented typing subset (inheriting the `tuple[X, ...]` rule from `799df4e`) and an unrepresentable annotation fails at inspection time rather than during a run.

**Typed parameters and results with explicit CRS/units.** `BufferRequest(layer_id, distance_metres, working_crs)` - all three required, so a caller cannot omit the CRS and let it default; `CentroidRequest(layer_id)` has no distance and no working CRS. Validation sits where the knowledge is: pure code refuses an unspecified CRS ("a distance without a stated CRS is ambiguous"), and the native adapter refuses a working CRS that is invalid, geographic (a distance there would be degrees) or not in metres (`EPSG:2227` is US survey feet). The metres interpretation is also proven positively: buffers 500 m and 1500 m apart in distance differ in extent width by 2000 m, which cannot happen if the distance were applied in degrees.

**Non-destructive outputs.** `Algorithms.execute` writes a new output into a per-run temporary directory and opens it as a layer the runtime owns; no step edits the source. The intermediate reprojection a buffer needs is deleted on success, and a failing run removes its own run directory before re-raising. `invoke` validates the inputs type, reads cancellation, runs, validates the result type, reads cancellation again, and only then calls `project.add_layer` - so a failure or cancellation at any point leaves the project untouched.

**Backends.** `Algorithms` contract in `qgis_sdk.services`, `FakeAlgorithms` in `qgis_sdk.testing`, `NativeAlgorithms` in `qgis_sdk.adapters.qgis` (registered in that package's `__init__`). The `tests/services` fixture gained `algorithms`, so the new contract tests run against **both** backends unchanged. Writing them caught a real gap: the fake had been accepting an unknown `layer_id`, which the native adapter refuses.

**Reference algorithms.** `qgis_sdk.reference` ships the two operations decision-19's workflow runs: `BufferLayer` (`reference.buffer`) and `CentroidLayer` (`reference.centroid`), deliberately thin - typed request in, injected service, typed result out - because parameter and output conversion belongs to the adapter.

**Evidence (measured on this host).** QGIS 4.2.3-Belem do Para, Qt 6.11.2, Python 3.14.8, Linux x86_64, `offscreen`; 772 algorithms and the `native` provider registered. Pure suite `497 passed, 22 skipped`; native opt-in suite `553 passed, 6 skipped`; `tests/services` with the native backend `100 passed`. New files: `tests/test_algorithms.py` 37, `tests/services/test_algorithms_contract.py` 14 (7 per backend), `tests/services/test_algorithms_native.py` 12. Coverage `100.00%` (1296 statements); ruff check and format clean. Source preservation is verified by `sha256` of the fixture dataset before and after a real buffer.

**AC notes.** #1 - `describe_algorithm` inspects without constructing; `invoke` builds a fresh `AlgorithmContext` over a child scope per invocation and closes it. #2 - typed request/result models, required `working_crs`/`distance_metres`, geographic and non-metre refusals, new-output-only semantics. #3 - both the fake and the real Processing backend prove source preservation, cleanup (success and failure) and project addition after success.

**Not claimed.** No `QgsProcessingAlgorithm` subclass and no `createInstance`: the reference classes are not registered as QGIS provider algorithms, so Processing's own parameter widgets and phase callbacks are not exercised - the adapter drives QGIS's native algorithms instead. Cancellation is read at phase boundaries only; a running native operation is not aborted mid-flight (that needs a `QgsProcessingFeedback` bridge not qualified headlessly). No provider/catalog registration object yet (deferred; decision-11 marks it illustrative). No thread-affinity proof. No style step and no reference plugin in this task. The failure-cleanup test drives the cleanup path with a Processing stand-in that writes and then raises; QGIS failing mid-write was not reproduced deterministically headlessly.
<!-- SECTION:NOTES:END -->
