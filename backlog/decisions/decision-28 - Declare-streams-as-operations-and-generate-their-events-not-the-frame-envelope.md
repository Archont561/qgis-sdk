---
id: decision-28
title: Declare streams as operations and generate their events not the frame envelope
date: '2026-10-24 22:40'
status: accepted
---
## Context

[TASK-17](../tasks/task-17%20-%20Generate-checked-in-TypeScript-contracts-clients-and-validators.md)
AC #1 asks for DTOs, operation maps, **events** and clients generated from
Python. Two slices landed the first three for plugin actions
([decision-26](decision-26%20-%20Derive-the-bridge-allowlist-and-the-generated-client-from-one-declared-manifest.md))
and for the curated host surface
([decision-27](decision-27%20-%20Expose-curated-host-services-to-web-views-as-generated-namespaces.md)).
Streams were left out, and today they are the one part of the wire that is
declared nowhere:

- `Dispatcher.register_stream(BridgeOperation, factory)` allowlists a stream by
  hand, with a request schema and nothing that says what its events carry.
- `qgis_sdk.declarations` has `@action` only, so `describe_plugin` cannot
  mention a stream and a generated client cannot offer one.
- The client's `BridgeStreamEvent.payload` is `unknown`, and the kind unions
  (`data | progress | state`, `complete | error | cancelled | gap | disposed`)
  are written once in `qgis_sdk.bridge.streams` and once in `bridge.ts`.

Three questions have to be answered before the emitter grows, because each one
moves the wire in both languages.

## Decision

### 1. A stream is an operation in the shared id namespace

A stream is declared with its own id (`sites.watch`) next to the actions
(`sites.summary`), and the ids are unique **across** actions and streams. There
is no second namespace and no second id scheme.

The dispatcher already behaves this way: `register` and `register_stream` refuse
each other's ids, the handshake advertises one `operations` list, authorization
is decided per operation id, and the subscription limit is per view, not per
namespace. A separate namespace would have had to be invented on the host as
well, for no gain a page could see.

In the generated module the two share one tree: `operations.sites.summary(...)`
answers a promise, `operations.sites.watch(input, handlers)` opens a stream and
resolves with a handle. `OPERATIONS` lists both, so `OperationId` covers both.

### 2. The event schema is declared on the stream as `events: {kind: schema}`

A stream record carries `request` (the subscribe payload, strict like every
input) and `events`, a map from event kind to the payload schema of that kind.
It has no `result`: the reply to a `subscribe` call is the protocol's
acknowledgement, not something an author declares. A record with both `result`
and `events`, or with neither, is refused - the same "exactly one of" rule a
frame already obeys for `event` and `terminal`.

- Keys are a non-empty subset of the three event kinds
  (`data`, `progress`, `state`). Anything else is refused at declaration time,
  and the generator refuses it again rather than emitting a kind the kernel
  would never deliver.
- Values are described with result semantics: every dataclass field is
  required, and the generated validator is lenient about additive fields, because
  an event travels host → page exactly as a result does (decision-22).
- In Python the authoring form is
  `@stream(id=..., title=..., events={"data": Change, "progress": Progress})` on
  an ordinary or generator method whose parameters are the request. The return
  annotation is not part of the wire and is not described (it still has to
  resolve, like every annotation); the `events` map is the declaration.
- `PluginDescription` gains `streams`, serialized as a separate `streams` list
  next to `actions` (so the TypeScript parser and every existing action-only
  consumer keep working; a missing list reads as empty). `BridgeOperation` gains
  `events`, advertised in the handshake, and `Dispatcher.from_description` /
  `from_runtime` register declared streams through `register_stream` with the
  same keyword binding actions get.
- The host enforces what it advertises: an event whose kind the stream did not
  declare, or whose payload fails the declared schema, terminates the
  subscription with `error` instead of reaching a page as a guessing game. This
  is the stream analogue of `invalid_result`.

### 3. The generated module owns the payload types, not the frame envelope

The envelope - `protocol`, `subscription_id`, `seq`, exactly one of `event` or
`terminal`, the ordering check and the synthesized `gap` - stays in the
hand-written kernel (`BridgeClient` in `bridge.ts`). It is protocol, versioned
by `BRIDGE_PROTOCOL_VERSION`, not contract, fingerprinted per surface. The
generated module never sees a raw frame: it receives the kernel's already-parsed
`{kind, payload}` and typing the payload is the whole of its job.

For every declared stream the module emits:

- one named interface and validator per declared kind
  (`SitesWatchData`, `SitesWatchProgress`), registered like any object schema so
  nested objects get their own names;
- a discriminated union `SitesWatchEvent` of `{kind, payload}` pairs, and a
  predicate of the same name that narrows an event by its kind and validates the
  payload with that kind's validator;
- a member `watch(input, handlers, options?) => Promise<StreamHandle>` on the
  operations tree. The `open` helper validates the input strictly before the
  transport, and on the first event that does not match the declaration it ends
  the typed stream once with `{kind: "error"}`, closes the kernel subscription
  and suppresses the `disposed` the kernel then reports - the typed layer keeps
  the kernel's "every subscription ends exactly once".

The surface helpers (`StreamHandlers`, `StreamHandle`, `StreamEnd`,
`subscribe` on the client-like interface) are emitted only when the surface
declares a stream, under surface-specific names (`HostStreamHandlers` and so on)
so a page can still import both modules. A surface without streams renders
byte-for-byte what it rendered before, and its fingerprint does not move: the
`contract_fingerprint` view includes `streams` only when there are any, because
the digest describes a wire and a wire without streams did not change.

What is deliberately **not** generated: the kind unions and the frame shapes.
They remain in the kernel, and a Python test now pins `bridge.ts` to the enums
in `qgis_sdk.bridge.streams`, so the two copies cannot drift unnoticed while the
envelope stays hand-owned.

## Consequences

- AC #1 of TASK-17 is claimable for events: a plugin declares a stream in
  Python, and the generated client offers it with typed events, a strict request
  and a lenient event validator, without running QGIS or the handler.
- `PLUGIN_DESCRIPTION_SCHEMA_VERSION`, `HOST_SCHEMA_VERSION` and
  `BRIDGE_PROTOCOL_VERSION` stay at 1: the description gained a list, the
  handshake gained an optional field on operations, the envelope did not change
  and no frame carries anything new. The seq/gap/coalescing rules of decision-23
  are untouched.
- `CONTRACT_FINGERPRINT` of the sample plugin moves because the sample now
  declares a stream; `HOST_FINGERPRINT` does not, because the host declares none.
  The first host stream (`algorithms.execute`, decision-27) will use this
  machinery unchanged.
- A contract violation inside a stream is reported as an `error` end with the
  operation named in the message, reusing the kernel's precedent of a locally
  synthesized `gap`; a sixth, client-only end kind would have split the
  vocabulary the two languages share.
- React hooks (TASK-18) can bind to `StreamHandlers<E>` and `StreamHandle`
  directly; nothing in the generated surface depends on React or on a browser
  global.
