---
id: decision-10
title: Use dataclass authoring and schema driven TypeScript generation
date: '2026-10-16 07:43'
status: proposed
---
## Context

Authors want ordinary dataclasses and familiar Python typing rather than mandatory model inheritance or parallel hand-maintained TS interfaces. Static interfaces alone do not validate messages at runtime. Native validator dependencies also affect QGIS plugin ABI/platform packaging.

## Decision

Proposed: expose standard-library dataclasses and a documented Python typing subset as the DTO authoring surface. Derive a versioned API description with distinct input-validation/output-serialization schemas. Generate TypeScript DTOs, operation maps, thin callable clients, event payload/subscription types, stable error metadata, validators and contract identity from that description. Exclude injected host dependencies. Keep transport connection/correlation/reconnection logic in a shared TS runtime, not duplicated generated clients.

Differentiate required, omittable/defaulted and nullable fields; define enums/unions, nested models, constraints, integer limits, dates and binary representations. Unsupported types fail with actionable errors, not implicit any. Python and frontend independently validate the contract; frontend validation is not authorization. A fingerprint detects differences but is not a compatibility policy.

Evaluate apischema plus json-schema-to-typescript, or Pydantic TypeAdapter over ordinary dataclasses. Neither backend is selected. Check maintained releases, Python 3.11+ and the workspace's Python 3.14 compatibility, schema dialect/constraint semantics, coercion policy, recursive/union handling and packaging. apischema offers a pure-Python distribution; Pydantic brings pydantic-core when used at runtime. A codegen-only dependency still requires a matching production validator. py-ts-interfaces is read-only/unmaintained and is not the preferred foundation. Do not implement a broad custom Python-to-TS converter or introduce an HTTP server just for type generation.

Generation must be deterministic, support stale-output detection, and integrate with dev/build without hand-editing generated files. Runtime handshakes reject incompatible contracts. Validate with cross-language fixtures, round-trip properties and negative cases; compiled TypeScript declarations alone are insufficient.

## Consequences

- Authors can keep ordinary dataclasses; public contracts do not leak a generator-specific base class.
- Schema/validator implementation, constraint annotation syntax, exact generation command and compatibility policy remain open until a tested spike.
- Runtime bundling/licensing/ABI costs are evaluated before choosing a validator dependency.

## Confirmed validation-backend selection process (2026-10-16)

Run a compatibility spike before selecting the dataclass schema/validation backend. Compare apischema and Pydantic TypeAdapter using the supported Python/QGIS environments, constraints, coercion, recursive/unions, required/nullable/defaulted semantics, input/output schemas, TS generation and error diagnostics. ADR-3 now accepts pure-Python-first runtime bundling: a native backend cannot become mandatory without explicitly revisiting that policy. The architecture remains library-neutral; no validator is selected.

## Confirmed second-interview refinement (2026-10-16)

[decision-22](decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md) requires strict request decoding without implicit coercion, distinct compatible result evolution, and checked-in generated frontend bindings with CI drift checks. Include these in the validation-backend spike.

## Confirmed next evaluation and deployment boundary (2026-10-16)

Preserve pure-Python-first distribution and the dependency setup policy in
[decision-3](decision-3%20-%20Development-and-distribution-artifacts-are-separate.md).
Do not introduce a startup downloader/installer to make a native validator viable.
For controlled deployments, explicitly provisioned native dependencies are an
option, not a change to the ordinary plugin installation contract.

Next evaluate a pure-Python candidate at the existing durable DTO/validation/schema
contract seam, starting with whether apischema's historical Python 3.14 eager-
annotation failure is resolved or can be supported cleanly. Verify actual pure-wheel
resolution, strict rejection of coercion/unknown request fields, useful diagnostics,
deterministic schemas and Python/Ajv parity. Retain Hypothesis and BDD contract tests
in the normal suite; do not restore the removed spike tree or treat historical
results as current regression evidence.

The checked mashumaro → JSON Schema → json2ts/Ajv example remains test-only.
Mashumaro's default decoder is not the strict request validator. The current
jsonschema oracle also does not establish a pure-Python runtime solution: it brings
native rpds-py. No production backend is selected.

If no pure-Python candidate meets the contract and compatibility requirements,
explicitly revisit the packaging policy before adopting a mandatory native backend
such as Pydantic. Initially evaluate that alternative with administrator/developer-
provisioned dependencies and real QGIS target tests, not a plugin-managed installer.
Do not build a broad custom validator/converter merely to avoid native dependencies.
Conda packaging, Desktop/WebEngine behavior and the supported Python/platform matrix
remain independent qualification gates.

## Bounded evaluation outcome (2026-10-16)

The user authorized the next evaluation steps and the JSON-compatible safe-integer
policy recorded in ADR-22. Apischema **0.19.0**'s explicit pure wheel installs on
Linux/Python 3.14.8 with no runtime dependencies or native modules. However, the
ordinary eager-annotation request still raises `KeyError`; using future annotations
avoids that failure but strict decoding rejects integral `2.0`. General coercion
also accepts numeric strings, so it is not the fix. The bounded evaluation does not
qualify apischema as the backend; do not hide these issues with a broad custom
validator or silently require a changed authoring surface.

Pydantic **2.14.1 / pydantic-core 2.50.1**, using a narrow explicit integral-number
adapter with strict types, forbidden extras and safe bounds, is the leading
**controlled-deployment candidate**. Installed-wheel tests and generated numeric
Python/Ajv parity passed on the available Linux target; see doc-5 for exact scope
and an annotation-order/schema issue discovered during evaluation. This is not
production backend selection or approval for a mandatory native runtime.

Keep pure-Python-first ordinary plugin packaging unchanged. If proceeding with
Pydantic for controlled deployments, first agree that distribution scope, retain
administrator/developer provisioning, and qualify supported Windows/Linux QGIS
installations, dependency conflicts and native imports in clean targets. Real
Windows/Desktop/WebEngine, Conda packaging and broader contract behavior remain
unqualified. No startup installer is authorized by this evaluation.

## Agreed next milestone: optional controlled-deployment slice (2026-10-16)

Proceed next toward an **optional Pydantic adapter prototype** for explicitly
controlled deployments, rather than repeating small backend build probes. This
records the next implementation direction, not a completed adapter or final
production-backend selection. Keep the adapter boundary explicit and preserve the
ordinary plugin distribution policy in ADR-3: no mandatory native runtime,
automatic dependency installation or promise of a universally installable native-
backed plugin ZIP.

The milestone is one end-to-end contract slice:

```text
Request JSON → strict Pydantic validation → typed handler
             → result serialization → generated schema / Ajv validation
```

Use administrator/developer-provisioned dependencies. Keep Pydantic-specific types
and imports behind the optional adapter boundary so the default QGIS-free SDK
contracts remain usable without it. Follow ADR-22's numeric and strict-input policy;
do not enable blanket coercion. The existing mashumaro schema example remains
separate test-only evidence, not the implementation of this adapter.

Add durable Hypothesis and BDD tests at the agreed contract seam for valid/invalid
requests, safe structured error paths, required/defaulted/nullable distinctions,
result-reader versus result-writer behavior, and Python/generated-schema/Ajv
agreement. Preserve deterministic generation/drift checks. Do not restore the
removed spike tree or rely on ignored scratch checks as the regression gate.

After the slice works, qualify it in **clean supported Linux and Windows QGIS
installations**, including native imports and coexistence with another plugin
using Pydantic. Record exact QGIS/Python/platform/dependency versions and failures;
co-import or wheel availability alone is not qualification. Desktop/WebEngine and
Conda/package-delivery claims require their own relevant integration/build tests.

If qualification passes, explicitly review and approve native-backed runtime
support for the intended deployment scope before making it a product requirement.
If it fails, address the demonstrated deployment problem before expanding the
implementation. Do not close TASK-12 from prototype success alone; require proven,
landed work and distinguish remaining qualification from historical evidence.

## Optional controlled-deployment slice implemented (2026-10-16)

Implemented the bounded adapter prototype at
`qgis_sdk.adapters.pydantic.PydanticContractAdapter` with a separately imported
`SafeJsonInteger` Pydantic annotation. The adapter lazily imports Pydantic, validates
JSON requests strictly, dispatches a typed handler, serializes result defaults, and
emits separate request/result-reader/result-writer schemas. Safe SDK errors expose
structured paths and validator codes without copying rejected values. The explicit
`controlled-deployment` extra pins Pydantic 2.14.1; it is absent from base runtime
requirements and is never installed at startup.

Persistent Hypothesis, BDD, schema-generation, Python-oracle, Ajv, generated-TypeScript
and typecheck tests now exercise the slice against the shared contract corpus. This
implements the prototype milestone only; mandatory backend selection and clean
Windows/Linux QGIS, plugin coexistence, Desktop/WebEngine, and Conda/package-delivery
qualification remain open. See doc-5 for exact local validation and restore caveats.

## Validation-backend spike closeout (2026-10-17)

The backend spike ([TASK-12](../tasks/task-12%20-%20Evaluate-dataclass-validation-and-TypeScript-generation-backends.md))
asked for a comparison, a compatibility exercise, and a recorded recommendation
with blockers. All three are answered by evidence in
[doc-5](../docs/plans/doc-5%20-%20TASK-12-validation-backend-spike-evidence.md),
and the bounded optional Pydantic slice it proposed landed in `main` (PR #7,
`7287a54`, CI green; the numeric policy landed in PR #6, `c37dc73`).

**Recommendation: no mandatory runtime backend is selected.** Pydantic **2.14.1**
stays the leading controlled-deployment candidate behind the optional
`controlled-deployment` extra; apischema **0.19.0** is not selected; mashumaro
remains test-only schema export; the `jsonschema` oracle remains test-only.
[ADR-3](decision-3%20-%20Development-and-distribution-artifacts-are-separate.md)
pure-Python-first distribution is unchanged, and no startup installer or
download is authorized.

Distinguish the two evidence classes recorded in doc-5: the original
apischema/TypeAdapter comparison is **historical** (its harness was removed at
the user's request and cannot be rerun from the checkout), while the mashumaro
schema example and the Pydantic adapter slice are **durable, persistent tests**.
Closing TASK-12 records that the spike's question is answered; it is not
evidence of Windows/macOS QGIS qualification, clean-prefix plugin coexistence,
Desktop/WebEngine behavior, or Conda/package delivery.

**This decision stays `proposed`.** The authoring/generation direction becomes
accepted only when a production description, generator and backend are selected
and landed ([TASK-2](../tasks/task-2%20-%20Implement-Python-declarations-and-generated-plugin-description.md),
[TASK-17](../tasks/task-17%20-%20Generate-checked-in-TypeScript-contracts-clients-and-validators.md));
the current examples are test-only and are not a general SDK generator or public
operation. The remaining gates — tagged unions/recursion/advanced constraints,
Windows and clean Linux QGIS qualification with plugin coexistence
([TASK-23](../tasks/task-23%20-%20Qualify-candidate-QGIS-4-Windows-and-Linux-toolchains.md)),
Desktop/WebEngine lifecycle ([TASK-4](../tasks/task-4%20-%20Add-the-versioned-WebEngine-bridge-contract.md)),
and Conda/ZIP delivery ([TASK-8](../tasks/task-8%20-%20Build-a-validated-QGIS-installable-plugin-ZIP.md))
— must be proven before any native validator becomes mandatory, followed by an
explicit ADR-3 deployment-scope review.
