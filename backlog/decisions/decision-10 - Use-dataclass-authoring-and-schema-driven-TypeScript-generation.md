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
