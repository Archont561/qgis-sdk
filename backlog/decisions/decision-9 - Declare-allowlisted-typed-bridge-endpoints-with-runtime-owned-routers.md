---
id: decision-9
title: Declare allowlisted typed bridge endpoints with runtime owned routers
date: '2026-10-16 07:43'
status: proposed
---
## Context

FastAPI-like decorators are familiar, but QWebChannel is asynchronous RPC, not HTTP. Reference qgis-rust has useful domain namespaces, descriptions, channel sharing and cross-language vectors, but also implicit public-callable discovery, constructor rewriting, permissive empty permissions and silent native fallbacks to avoid.

## Decision

Proposed: offer explicit BridgeRouter endpoint decorators with typed request/result models and dependency injection. Support a small operation decorator first; query/command naming is an ergonomic option, not a promised pair of APIs. Stable operation IDs are independent of Python method names. Injected PluginContext/dependencies are host-only, excluded from input schemas. Exact Context/Depends syntax remains open. Routers attach explicitly to a plugin runtime, not a global registry; duplicate IDs fail checks/startup. Unmarked public methods are not exposed.

Use a versioned transport-independent description and request/response/event contract: request IDs, named argument objects, mutually exclusive result/error responses, stable structured error codes, separately typed events, and opaque session-scoped handles with expiration. Do not copy the reference repository's Rust engine target, engine transport or backend dependency into this Python-first SDK. Host services and plugin operations are separate capabilities. Standard Promise rejection is not a statically typed error union; an explicit Result API is optional if exhaustive error handling is required.

Authorize on the Python host, deny by default (an empty permission set grants nothing), validate input and serialized results, restrict origins/navigation and keep secrets/native objects on the host. Do not expose arbitrary Python invocation, eval, iface or raw Qt replies. Capability permission does not sandbox compromised frontend code within allowed capabilities.

Use one QWebChannel per transport, with defined readiness, failed initialization/timeouts, disposal and reconnection. Page reload recreates the JS world; reconnect, handshake and resubscribe explicitly. Plugin reload additionally invalidates old endpoints/handles. Unload rejects new calls, cancels/detaches work and prevents callbacks into deleted objects. Production loads packaged assets; local dev origins and remote debugging are explicit. Missing WebEngine or failed registration is a real error, not automatic test fallback.

Declare scheduling/thread affinity before supporting async handlers. A JS Promise or async def alone does not move PyQGIS work off the GUI thread; define scheduler, GUI-thread handoff, cancellation and progress semantics separately.

## Consequences

- Native-only plugins do not require WebEngine/TypeScript.
- Domain services serve both Python and bridge adapters; do not embed the service layer inside the bridge package.
- Share typed transport plumbing and contract vectors, but verify runtime conformance rather than assuming a testing contract is implemented everywhere.
- Reference inspected: Archont561/qgis-rust commit ba03fa042e2e2f3dad79b492d8957316e7a9a52c, particularly plugin/decorators.py, bridge/description.py, bridge/runtime.py, bridge/qgis_api/api.py, TS channel.ts and .knowledge/bridge-test-contract.md. This was source inspection, not execution of its tests.

## Confirmed bridge policy (2026-10-16)

ADR-18 accepts a broad host capability surface, host-enforced per-view allowlists and versioned compatibility that may permit explicitly compatible additive changes. Do not equate fingerprints with compatibility or plugin-wide access with view authorization. The exact operation inventory, permission/resource constraints, compatibility algorithm and endpoint syntax remain open.

## Confirmed second-interview refinement (2026-10-16)

[decision-20](decision-20%20-%20Enforce-scoped-host-authority-and-stale-reference-failures.md) accepts scoped handles, explicit file grants, constrained host networking and separate browser resource/navigation enforcement. [decision-22](decision-22%20-%20Use-strict-inputs-extensible-results-and-experimental-contracts.md) accepts strict requests, extensible compatible results and safe typed errors. Mechanisms and exact schemas remain open.

## Proposed Tauri-inspired invocation refinement (2026-10-16)

[decision-23](decision-23%20-%20Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md) proposes one narrow dispatcher boundary, generated typed clients, trusted host caller identity, distinct request/event/stream semantics, ownership-aware resource release and injected transport mocks. This extends rather than replaces the accepted permission, compatibility, error and cancellation policies. Native QWebEngine evidence remains separate from mock conformance.
