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