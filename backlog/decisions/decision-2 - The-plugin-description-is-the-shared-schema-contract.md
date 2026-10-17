---
id: decision-2
title: The plugin description is the shared schema contract
date: '2026-10-15 23:05'
status: accepted
---
## Context

A plugin may expose Python-defined actions, forms, views, and signals to native Qt widgets or a TypeScript UI in QWebEngine. Those consumers need a stable, inspectable contract, but the contract must not duplicate Python handler logic or leak arbitrary Python/QGIS objects over the JavaScript boundary.

## Decision

The SDK will derive one inspectable plugin description from the Python declarations. It is the shared contract for SDK tooling and UI renderers. A versioned JSON representation may be generated from it for transport/interchange, including the TypeScript bridge. It describes supported metadata, identifiers, field constraints, actions, and UI bindings; it does not contain executable Python behavior. Python handler methods implement behavior and receive validated values through the SDK runtime.

## Consequences

- Description generation and validation should be deterministic and testable without launching QGIS.
- Contract evolution requires an explicit schema/version compatibility policy.
- Native Qt and WebEngine renderers should be adapters over the same declarations rather than parallel authoring systems.
- JavaScript bridge messages must use serializable DTOs and an allowlisted operation surface, never raw Qt or QGIS objects.

## Proposed contract refinement (2026-10-16)

Derive endpoint request/result/event schemas from ordinary dataclasses and supported annotations; omit injected host dependencies. Distinguish nullable, required and omittable fields, reject unsupported types, and generate TS DTOs/operation maps/clients plus runtime validators. Keep API/protocol identity and compatibility policy explicit. See [decision-9](decision-9%20-%20Declare-allowlisted-typed-bridge-endpoints-with-runtime-owned-routers.md) for allowlisted router/transport behavior and [decision-10](decision-10%20-%20Use-dataclass-authoring-and-schema-driven-TypeScript-generation.md) for generation/backend evaluation. These refinements do not select a validation library or final decorator syntax.

## Confirmed TASK-2 foundation (2026-10-17)

The user approved a typed `PluginDescription` with deterministic versioned JSON
and action metadata/request/result schemas, without callables or host objects.
The implemented initial representation uses `schema_version: 1`, plugin ID/title,
and ID-sorted actions with binding names and JSON Schema 2020-12 keyword subsets.
Request inputs are keyed by method parameter name; result schemas describe the
writer, not an extensible reader. Defaulted request fields are omittable; result
writer fields are all required. Nullable types remain distinct from defaults.
This bounded stdlib-only structural exporter does not select a runtime validation
backend, TypeScript generator, lifecycle protocol, or compatibility algorithm.
Unsupported annotations fail explicitly; the test-only backend-spike exporters
remain separate evidence. See the package README for format and type limits.
