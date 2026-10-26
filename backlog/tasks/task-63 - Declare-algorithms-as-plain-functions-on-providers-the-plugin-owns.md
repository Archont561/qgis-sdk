---
id: TASK-63
title: Declare algorithms as plain functions on providers the plugin owns
status: Done
assignee: []
created_date: '2026-10-26T08:27:00Z'
updated_date: '2026-10-26 12:20'
labels: []
milestone: m-5
dependencies:
  - TASK-59
type: enhancement
ordinal: 63000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-42. Provider.algorithm decorates a plain function: AlgorithmContext first, typed keyword inputs, typed return, id/title derived from the name as for @job. LayerInput, CrsInput and Metres become annotation aliases over the LayerParameter, CrsParameter and MetresParameter markers. A @plugin class lists providers = [...]; PluginRuntime.start() registers them with the host's Processing registry when the context has the native services and unload() removes them; duplicate provider ids are refused by name. invoke(function, ctx, *, progress, cancellation, add_to_project, **inputs) runs one from any context carrying algorithms, project and scope, with a fresh AlgorithmContext per call. The class form (@algorithm on a class, run(inputs), invoke(Class, Request), public register_provider glue) is removed; qgis_sdk.reference becomes functions on reference_provider. describe_plugin and the wire contract do not change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 @provider.algorithm accepts a function and refuses at decoration a missing leading context parameter, an input outside the parameter kinds, and a duplicate id; describe_algorithm(function) reports inputs, kinds, required names and the result; LayerInput/CrsInput/Metres are aliases and the Annotated[..., LayerParameter()] spelling describes identically; pure tests cover each.
- [x] #2 A @plugin class with providers = [...] has them registered in QgsApplication.processingRegistry() after start() and removed after unload() (native test under qgis_app); the same class over the fakes registers nothing; two plugins sharing a provider id are refused by name; describe_plugin output and HOST_FINGERPRINT are unchanged.
- [x] #3 invoke(function, ctx, **inputs) runs from a PluginContext, a JobContext and an AlgorithmContext with a fresh AlgorithmContext each time, honours progress, cancellation and add_to_project, and raises the existing QgisSdkAlgorithmRejectedError / QgisSdkAlgorithmCancelledError; the toolbox adapter calls the same function with the same context type (services native suite).
- [x] #4 The class form, bare @algorithm, invoke(Class, Request) and public register_provider are gone from the API and the docs; qgis_sdk.reference is rewritten on reference_provider; doc-12 migration notes list every rename; the Python suite, tests/scripts, the example and the native services harness are green.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Shipped in the m-5 sprint 1 PR. Runtime: qgis_sdk.algorithms now exposes describe_algorithm / invoke(fn, ctx, **inputs) / parameter_kind / AlgorithmDescription (kinds, required, result_schema); qgis_sdk.providers gained ProviderDescription + declared_providers and Provider.algorithm validates at decoration (leading AlgorithmContext, parameter kinds, duplicate id, VectorLayerInfo result); LayerInput/CrsInput/Metres are Annotated aliases over LayerParameter/CrsParameter/MetresParameter. Lifecycle: @plugin classes list providers = [...], PluginRuntime.start()/unload() register and remove them through the new PluginContext.processing capability (services.Processing protocol, adapters.qgis.NativeProcessing, testing.FakeProcessing); duplicate provider ids are refused by name; describe_plugin output and HOST_FINGERPRINT sha256:f96bdf10... unchanged. Contexts: JobContext.algorithms/project, AlgorithmContext.project (JobService(algorithms=, project=)). Removed from the public API: the class form, bare @algorithm, invoke(Class, Request), AlgorithmResult, RegisteredAlgorithm, parameter_kinds, adapters.qgis.register_provider; qgis_sdk.reference is buffer_layer/centroid_layer on reference_provider (ids unchanged). doc-12 rewritten (algorithms, providers, module table, decorator list) with a full rename list in the 0.6.0 migration notes. Validation: Python suite 1505 passed / 43 skipped; QGIS_SDK_NATIVE_SERVICES=1 services 134 passed; test-reference-example 17 + 5 passed (new toolbox test); QGIS_SDK_REFERENCE / HEADLESS_LIFECYCLE / DESKTOP_ADAPTER / PLUGIN_COEXISTENCE / DEVTOOLS harnesses green; tests/scripts 241 passed; ruff check + format, biome, actionlint, typecheck, test-reference-web green.

Follow-up (same day, after #92): qgis_sdk.reference removed from the runtime; the example owns its algorithms in examples/simple/simple/algorithms.py (provider id simple) and the runtime tests use tests/sample_algorithms.py. Recorded as a dated status review on decision-42; doc-12 migration notes updated.
<!-- SECTION:NOTES:END -->
