---
id: decision-7
title: Use layered pytest fixtures properties and behavioural contracts
date: '2026-10-16 07:43'
status: accepted
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

## Status review (2026-10-26): promoted to `accepted`

Re-checked while re-planning the milestones after 0.5.0. Everything the
Decision section proposes now exists in the tree, so the status moves to
`accepted`:

- The pure harness is `qgis_sdk.testing` (fakes behind every service
  contract, captured calls, scripted network replies, a deterministic
  scheduler) and the opt-in native fixtures are `qgis_app` /
  `webengine_profile` in `packages/qgis-sdk-python/tests/conftest.py`, which
  skip on QGIS-free runners instead of importing `qgis` at collection time.
- The three layers are all present and run in the gate: ordinary pytest
  examples, Hypothesis properties (16 modules, including the stream-ordering
  state machine in `test_bridge_streams_properties.py`) and pytest-bdd
  scenarios under `tests/features/` with `bridge_steps.py`.
- Shared contract tests run against fakes and, behind
  `QGIS_SDK_NATIVE_SERVICES=1`, against the native adapters; the harnesses
  are opt-in environment variables, one per process, and an explicitly
  requested but unavailable runtime fails the run rather than skipping it.
- Python and TypeScript validate the same checked-in bridge vectors
  independently (`tests/contracts/` on both sides, decision-10/23).

Direct pytest stays the primary route; `qgis-sdk test` is the thin wrapper
decision-8 asked for. Nothing in the Decision section is unimplemented.
