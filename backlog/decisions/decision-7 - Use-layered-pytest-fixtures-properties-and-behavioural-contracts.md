---
id: decision-7
title: Use layered pytest fixtures properties and behavioural contracts
date: '2026-10-16 07:43'
status: proposed
---
## Context

Plugin authors need convenient fixtures, while SDK maintainers need evidence for pure contracts, lifecycle sequences, and actual QGIS behavior. A fake context and a real initialized QGIS application prove different things.

## Decision

Proposed: expose an opt-in pytest plugin with a function-scoped pure harness (illustrative fixture name `sdk_ctx`). The harness exposes a production context backed by fakes plus test-only setup, captured calls, scripted network responses and a deterministic scheduler. Fresh state and teardown cover resource disposal, pending work and unmet expectations. Unsupported native operations fail explicitly; never silently substitute a fake for an integration runtime.

Use separate opt-in native fixture modules. A session-scoped real headless QgsApplication supports PyQGIS integration without Desktop; isolate project state per test where injection permits. Singleton project state, settings, registries and caches require their own cleanup. Own one application per process, on the main thread; do not destroy an externally owned app. Processing providers, GUI/display and WebEngine setup need explicit capability checks. A standalone app supplies no real Desktop iface; genuine plugin discovery, menus/toolbars and lifecycle require actual QGIS Desktop with an isolated profile. Parallel processes do not share one application singleton, but shared profiles/files/native resources still need an isolation policy.

For the SDK itself, combine ordinary pytest examples, Hypothesis properties/state machines and pytest-bdd scenarios:

- Properties cover deterministic descriptions, schema round-trips, JSON-compatible values, invalid-input rejection, dispatch exactly once, safe ZIP paths, and explicit permission boundaries.
- Stateful properties cover startup/partial failure/unload, repeated close, cancellation, expired handles and late callbacks using controlled scheduling rather than sleeps.
- Behavioral scenarios describe observable author workflows: invalid input never invokes handlers; unloading removes owned actions; denied operations never run; packaging excludes development files.
- Native/fake implementations share applicable service contract tests. Real provider/geometry/GUI behavior is verified only with native integration tests.
- Python and TypeScript independently validate shared versioned bridge vectors; fixed examples and negative cases complement generated tests so round-trips do not merely reproduce one implementation's error.

Keep pure tests collectable without QGIS: markers alone cannot stop top-level native imports. Explicitly requested unavailable runtimes fail before claiming a green gate. Direct pytest remains supported, not just the CLI wrapper.

## Consequences

- Separate pure, Qt/QGIS, Desktop and optional WebEngine gates with visible runtime diagnostics.
- Fixture names and exact pytest registration/layout remain provisional; avoid surprising auto-loading in unrelated suites.
- CI uses bounded reproducible Hypothesis profiles, larger exploration where useful, and regression cases for discovered failures. Coverage alone is not evidence of contract correctness.
