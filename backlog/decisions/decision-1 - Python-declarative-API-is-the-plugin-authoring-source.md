---
id: decision-1
title: Python declarative API is the plugin authoring source
date: '2026-10-15 23:05'
status: accepted
---
## Context

The SDK is intended to let plugin authors express plugin structure and UI in Python, while ordinary Python methods provide the actual behavior. A separate hand-maintained JSON/schema definition would create a second source of truth and make it harder to use normal Python types, validation, and editor tooling.

## Decision

Use a Python-first declarative authoring API, including decorators and typed declarations, as the source of plugin and UI logic. Plugin handlers remain normal Python methods. The SDK may inspect these declarations and generate a description or serialized schema for renderers and cross-language consumers, but authors do not separately maintain a JSON description as the authoritative definition.

## Consequences

- Python is the primary authoring language and runtime for v1.
- Decorators/declarations need stable, inspectable metadata and useful type-checking/editor behavior.
- The API must make the boundary between declaration and handler behavior clear.
- Any generated JSON is an output/interchange format, not the source of truth; it needs validation and versioning.
- A TypeScript/WebEngine UI can consume generated descriptions without moving plugin behavior out of Python.