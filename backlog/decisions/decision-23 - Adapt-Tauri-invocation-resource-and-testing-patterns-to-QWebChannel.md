---
id: decision-23
title: Adapt Tauri invocation resource and testing patterns to QWebChannel
date: '2026-10-16 09:11'
status: proposed
---
## Context

Source inspection of tauri-apps/tauri at commit 136a28eaa879e8aa706f9b2e05a050c46dcc1f4f identified useful invoke, channel, resource, authority and mock patterns. This is a proposed adaptation to the accepted Python/QWebChannel architecture, not a dependency on Tauri, a Rust requirement, or evidence that its runtime/security guarantees transfer to QGIS. No Tauri tests were executed.

## Decision

Proposed: keep a small transport-independent invocation kernel and generated operation-specific public clients. Raw invoke<T>(string, args) does not prove command existence, argument correctness or response shape. Generated wrappers provide compile-time operation/input/result relationships and runtime response validation. Keep injected dependencies out of the wire schema.

Expose a narrow QWebChannel transport endpoint to a Python dispatcher rather than directly registering arbitrary author controller objects. Derive caller view/origin/runtime generation from trusted host-owned endpoint/session state, never a request body's claimed view ID. Centralize envelope/registry resolution, capability/resource authorization, input validation, execution and result/error encoding. Define validation/authorization failure precedence and redaction so diagnostics do not leak privileged information. All invocation paths, including any low-level escape hatch, enforce the same boundary.

Separate request/response, state-change subscriptions and operation-scoped streams. Define ordered sequence scope, terminal events, subscriber exceptions, cancellation, completion, disposal, reconnect and stale-generation behavior. Ordered delivery is not backpressure: bound buffering and choose explicit overflow/gap behavior. Progress can be coalesced if its contract permits; data streams must not silently drop payloads. Job handles may hide channel mechanics. Tauri Channel is a logical stream, not the QWebChannel transport.

Make resource release explicit and ownership-aware. Closing a subscription disconnects it; releasing a borrowed project-layer handle must not remove the layer. Only an explicitly owned temporary resource may be destroyed by its lifecycle policy. Host cleanup on view/runtime disposal is required even if JS references disappear. Define repeated close, in-flight close and post-close calls. Do not rely on frontend garbage collection to release native resources.

Mock the invocation boundary using an injected transport per client, not mandatory mutation of global browser internals. Provide typed handlers, captured calls, scripted faults/events and leak/unmet-expectation checks. Use independent clients to prove isolation. Mocks do not establish native QWebEngine/authorization behavior.

Promise resolution is not a threading, cancellation or retry guarantee. A local timeout/AbortSignal may stop waiting while host execution continues; distinguish that from acknowledged cancellation. Do not automatically retry unknown-outcome invocations. Keep GUI-thread execution and owned-job rules from ADRs 4/21; defer Rust as accepted in ADR-5.

## Consequences

- Adopt simplicity and explicit lifetime boundaries, not Tauri-specific globals, numeric resource IDs, Rust drop semantics, callback eval plumbing or binary transport assumptions.
- Raw/binary/streaming optimizations need QWebChannel-specific measurement and bounded transport design; they are not required simply because Tauri supports them.
- Public API names, stream limits, overflow behavior, cancellation messages and dispatcher interface remain open pending tests/spikes.
- TASK-4 owns bridge implementation/type/client/transport acceptance; TASK-7 covers the corresponding Python fixtures, behavioral/property tests and native qualification separation. No completion is claimed.

## Source references

- [Frontend invoke, Channel and Resource](https://github.com/tauri-apps/tauri/blob/136a28eaa879e8aa706f9b2e05a050c46dcc1f4f/packages/api/src/core.ts)
- [Channel ordering/lifetime](https://github.com/tauri-apps/tauri/blob/136a28eaa879e8aa706f9b2e05a050c46dcc1f4f/crates/tauri/src/ipc/channel.rs)
- [Caller-aware authority](https://github.com/tauri-apps/tauri/blob/136a28eaa879e8aa706f9b2e05a050c46dcc1f4f/crates/tauri/src/ipc/authority.rs)
- [IPC mocks](https://github.com/tauri-apps/tauri/blob/136a28eaa879e8aa706f9b2e05a050c46dcc1f4f/packages/api/src/mocks.ts)

## Stream limits, settled 2026-10-24

The limits this decision left open are now fixed by `qgis_sdk.bridge.streams` and
its tests, and the choice is deliberately conservative:

| Question | Answer | Why |
| --- | --- | --- |
| Sequence scope | one counter per subscription, starting at 0 | a gap in one stream says nothing about another |
| Buffer bound | 64 frames per subscription, 8 subscriptions per view | a stalled view must not grow the host's memory |
| Pull overflow | impossible - the source is not pulled | a pull model has natural backpressure |
| Push overflow | subscription ends with `gap` and a dropped count | losing events silently is worse than saying so |
| Coalescing | progress only, and only while queued | data payloads are never merged or replaced |
| Terminal | exactly one of `complete`/`error`/`cancelled`/`gap`/`disposed` | every end is a frame the client can act on |
| Disposal | idempotent; `disposed: false` when already gone | a closing UI races the terminal frame |
| Generation advance | sources closed, no frames delivered | a stale view cannot be trusted to interpret state |
| Protocol version | stays 1 | the client only sees frames for subscriptions it opened |

Status stays `proposed`: the invocation, authority, stream and resource patterns
are implemented and tested, but the Qt half of the adapter has not yet carried a
real page's traffic (TASK-22), and this decision should not read as qualified
before that happens.
