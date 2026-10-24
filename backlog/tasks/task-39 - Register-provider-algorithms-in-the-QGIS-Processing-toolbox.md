---
id: TASK-39
title: Register provider algorithms in the QGIS Processing toolbox
status: Done
assignee: []
created_date: '2026-10-24 15:49'
updated_date: '2026-10-24 15:53'
labels: []
milestone: m-1
dependencies: []
priority: high
type: feature
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Give @algorithm a FastAPI-like Provider so a plugin declares one provider object and registers algorithms on it with @provider.algorithm, and those algorithms appear in the QGIS Processing toolbox as provider:algorithm and run through the Processing framework. The QGIS side needs a QgsProcessingProvider and one QgsProcessingAlgorithm per registration, with the typed request dataclass fields mapped to Processing parameters (layer, CRS, metres, primitives) and the produced layer copied into the requested output sink. Only the documented slice: no GUI widgets beyond QGIS defaults, no thread-affinity claim, no arbitrary Processing operations beyond what the Algorithms service offers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A Provider object accepts registered algorithm classes through a decorator, refuses a duplicate id, and describes itself with each algorithm's request/result schema.
- [x] #2 The QGIS adapter registers a provider whose algorithms are visible in the Processing registry as provider:algorithm and execute through processing.run.
- [x] #3 Typed request fields map to Processing parameters (layer, CRS, metres, str/int/float/bool) and an unrepresentable field is refused at registration rather than at run time.
- [x] #4 Real Processing tests prove execution returns the produced layer to the requested sink, leaves the source dataset untouched, and that unregistering removes the algorithms.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 completed. A provider is now the object a plugin declares its algorithms on, and the QGIS adapter turns it into a real Processing provider.

**Pure side.** `qgis_sdk.providers.Provider(id=..., title=...)` with `@provider.algorithm(id=..., title=..., group=...)`. Registration is validated where the author can see it fail: the class must have its own typed `run`, the request must describe under the documented schema subset, every request field must map to a host parameter, and the id must be unique in the provider. A class already declared elsewhere is refused, and a refused registration removes the marker again, so it cannot leave a half-declared class that describes but is never registered. `describe()` returns `provider:algorithm` qualified ids plus each algorithm's parameter kinds.

**Parameter mapping.** New `qgis_sdk.models.parameters` markers - `LayerInput()`, `CrsInput()`, `Metres()` - ride in `Annotated` metadata. `declarations._schema` now unwraps `Annotated`, so the wire schema still describes the stored type (`Annotated[str, LayerInput()]` -> `{"type": "string"}`) while the host learns intent. Plain `str`/`int`/`float`/`bool` map to text/integer/double/boolean. Anything else (nested dataclass, list, `Literal`) is refused at registration with the field name and the supported kinds - never guessed at run time.

**QGIS bridge.** `qgis_sdk.adapters.qgis.register_provider(...)` builds a `QgsProcessingProvider` and one `QgsProcessingAlgorithm` per registration, so `provider:algorithm` appears in the Processing toolbox, the modeler, batch mode and `processing.run`. `processAlgorithm` maps the widget values back into the typed request dataclass (a picked layer is opened through the same `Layers` service, so it arrives as an owned layer id), calls `invoke(..., add_to_project=False)`, and copies the produced layer's features into the destination the user chose. `add_to_project=False` exists because QGIS owns the destination here and a second project layer would be a duplicate.

Two deliberate decisions: `flags()` returns `FlagNoThreading` because worker-thread execution of these adapters is not qualified, and the bridge exposes `unregister()` because `QgsProcessingProvider` has no public removal method in QGIS 4.2 - the registry owns removal.

**Evidence.** Pure suite `521 passed, 32 skipped`; native opt-in suite `587 passed, 6 skipped`; coverage `100.00%` (1419 statements); ruff check and format clean. New tests: `tests/test_providers.py` 23 pure, `tests/services/test_provider_registration_native.py` 10 real-QGIS. The native tests prove the registry advertises `reference:buffer` and `reference:centroid`, that metadata and parameter order match the request dataclass, that `processing.run` writes 3 features into the requested GeoPackage with the source dataset byte-identical, that a refused request surfaces as a Processing error and creates no file, that unregistering removes the algorithms, that a second registration of the same provider is refused, and that a user-declared provider runs exactly like the shipped one.

**AC notes.** #1 - `Provider`, duplicate-id refusal, `describe()` with schemas, groups and qualified ids. #2 - algorithms visible in the Processing registry and executable via `processing.run`. #3 - `parameter_kinds` mapping plus registration-time refusal, with the field and the supported kinds named. #4 - the native tests above.

**Not claimed.** No GUI beyond QGIS's generated dialog (no custom widget for a parameter), no thread-affinity proof (`FlagNoThreading` instead), no automatic registration (the plugin calls `register_provider`), and no style or refinement step inside a provider run. Algorithms still run only the operations `Algorithms` offers; a provider exposes them, it does not invent new ones.
<!-- SECTION:NOTES:END -->
