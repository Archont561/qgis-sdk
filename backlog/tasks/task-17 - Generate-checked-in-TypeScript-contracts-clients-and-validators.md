---
id: TASK-17
title: Generate checked in TypeScript contracts clients and validators
status: To Do
assignee: []
created_date: '2026-10-16 12:02'
updated_date: '2026-10-24 19:41'
labels: []
milestone: m-2
dependencies:
  - TASK-2
  - TASK-12
references:
  - >-
    backlog/decisions/decision-10 -
    Use-dataclass-authoring-and-schema-driven-TypeScript-generation.md
  - >-
    backlog/decisions/decision-22 -
    Use-strict-inputs-extensible-results-and-experimental-contracts.md
  - >-
    backlog/decisions/decision-23 -
    Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md
  - doc-8
priority: medium
type: feature
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Generate checked in TypeScript contracts clients and validators. Implement only the documented slice; proposed mechanisms require evidence before finalizing. Focused tests are part of this task, not deferred to a later test milestone.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Generate deterministic DTOs/operation maps/events/clients from Python without running QGIS or handlers.
- [x] #2 Compile-time tests reject invalid names/arguments; runtime tests reject malformed responses with asymmetric additive compatibility.
- [x] #3 Unsupported annotations fail rather than emit any; CI drift checks protect generated-file ownership.
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-21 21:56
---
blocked-by-actions (doc-8): AC3 ('CI drift checks protect generated-file ownership') cannot be satisfied while every job fails to start. The local stand-in is `bun run sdk:generate` followed by `git status --porcelain`: it proves no drift for one change, which is not the protection AC3 asks for. Keep AC3 unchecked and wire it when runners return.
---

author: qgis-sdk agent
created: 2026-10-24 15:22
---
From the TASK-25 closeout (native services, m-1): the two new bridge-eligible payload types - qgis_sdk.models.VectorLayerInfo (field_names: tuple[str, ...]) and StyleSpec (required_fields: tuple[str, ...]) - are NOT expressible by the current contract generator. Probe: _schema(VectorLayerInfo, 'probe') raises QgisSdkDeclarationError: 'probe.field_names: unsupported annotation tuple[str, ...]; use JSON primitives, list, union, Literal or a dataclass'. No TS generation exists yet, so nothing is broken today, but this task will meet it: either extend the documented annotation subset to tuple[X, ...] (same JSON array as list), or change those fields to list[str] before the wire contract freezes. Deciding after the fake/native adapters and tests depend on the tuple spelling costs a multi-file change. Reference: doc-11 records the native service surface this would expose.
---

author: qgis-sdk agent
created: 2026-10-24 15:27
---
Resolved on 2026-10-24 (option A, user-chosen): the generator now accepts tuple[X, ...] and emits the same schema as list[X], while fixed-length and bare tuples are refused with a specific message. Commit landed with 9 declaration tests plus a guard that VectorLayerInfo and StyleSpec stay generatable, and the checked-in contract fixtures regenerate byte-identically. decision-10 carries a dated amendment and stays proposed until this task produces real generated TypeScript. Nothing about this task's scope changed - the payload blocker recorded in the earlier comment is cleared.
---
author: qgis-sdk agent
created: 2026-10-24 21:45
---
Input contract settled by [decision-26](../decisions/decision-26%20-%20Derive-the-bridge-allowlist-and-the-generated-client-from-one-declared-manifest.md) and implemented on the host side: `BridgeOperation` carries the declared request/result schemas, `Dispatcher.from_description`/`from_runtime` project the allowlist from the same `PluginDescription` the handshake advertises, and both directions are validated (`invalid_payload` with the field path in, `invalid_result` out).

What that means for this task: the generator reads one manifest - the plugin description - and the dispatcher the frontend will actually talk to reads the same object, so a generated client cannot name an operation the host does not expose without the declaration itself changing. The remaining work here is emission and drift control: DTOs, operation map, callable client, validators, a `contract_fingerprint`, and the `--check` mode CI runs.

Not decided here: the tuple/`Literal`/`anyOf` subset the emitter must refuse loudly (it mirrors `qgis_sdk.declarations`, which already refuses what it cannot describe), and whether a strict `tryX` result union ships alongside the throwing form. [decision-27](../decisions/decision-27%20-%20Expose-curated-host-services-to-web-views-as-generated-namespaces.md) adds the second surface (curated host namespaces) as a proposal, not as scope for this task.
---
2026-10-24 (first slice of the generator):
- `packages/qgis-sdk/src/qgis_sdk/bridge/generate.py` turns one `PluginDescription` into one TypeScript module - interfaces, `OPERATIONS`/`OperationId`, validators, `PluginOperations`, `createOperations(client)` - plus `contract_fingerprint` and `check_generated`. The CLI verb is `qgis-sdk bridge generate`.
- AC #2 is met from both ends: `packages/qgis-sdk-bridge/tests/generated.types.ts` fails the build for an unknown operation id, a misspelled member, a missing or mistyped argument, an unknown nested property and a bad literal; `packages/qgis-sdk-bridge/tests/generated.test.ts` covers the runtime half, where a request is closed (unknown arguments refused before the transport) and a response is additive (a field a newer host added is tolerated, a missing one is a `ContractError`).
- AC #3 is met: an unsupported construct (`$ref`, any keyword outside the declared subset, an object inside a union, a fixed-length tuple losing its shape) raises `QgisSdkBridgeError` instead of emitting `any`, and the generated file is owned by CI - `Check the generated bridge client is current` regenerates it, prints the diff and fails on a dirty tree, with `--check` as the same comparison for a developer.
- AC #1 is met for DTOs, operation maps and clients. It is **not** claimed for events: stream frames still have hand-written types on the client side, so generated event/stream types and the host namespaces (slice 3) remain open.
- Verification: `test_bridge_generate.py` 24, TypeScript 123 pass, `tsc --noEmit` clean, ruff clean; the checked-in artifact is regenerated by CI rather than trusted.
<!-- COMMENTS:END -->
