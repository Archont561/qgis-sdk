---
id: decision-27
title: Expose curated host services to web views as generated namespaces
date: '2026-10-24 21:20'
status: accepted
---
## Context

A plugin's web view should be able to do what the plugin's Python can do: read
layers, publish notifications, resolve a packaged style, read a setting. Today
the bridge offers invocations, subscriptions and release, but no host surface,
so a frontend either goes through a plugin-declared action for everything or
does not exist.

What a plugin actually has is not "the QGIS API" but five curated Protocols in
`qgis_sdk.services` - `Layers`, `Project`, `Settings`, `Styles`, `Notifications`
- plus `Algorithms`. They are deliberately small and already QGIS-free, which
makes them a good wire surface. They also contain hazards that a naive
"expose everything" would hand to a page:

- `Layers.open_vector(source: Path)` takes a **filesystem path**. Exposed as-is
  to a web view it is arbitrary local file read.
- `Project.add_layer` and `Settings.set` mutate user-visible state.
- `Layers.selection(layer_id)` returns every selected index; a selection can be
  hundreds of thousands of rows.
- `Algorithms.execute` is long-running and needs progress and cancellation, not
  a request/response that times out into an unknown outcome.
- Every one of these must run on the thread QGIS was qualified on.

[decision-18](decision-18%20-%20Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md)
already says the host API direction is broad while "the exact operation
inventory is still to be specified", and
[TASK-20](../tasks/task-20%20-%20Enforce-scoped-file-network-and-browser-resource-authority.md)
owns file/resource authority. So the inventory question is real, not cosmetic.

## Decision (proposed)

**Expose the curated services as generated namespaces, in two surfaces with two
owners.**

- **`host`** - generated from a `HostManifest` declared next to
  `qgis_sdk.services`, shipped *inside* `@archont561/qgis-sdk` and
  versioned with it. Every plugin's frontend gets `host.layers.*` without a
  build step, and the surface cannot drift from the npm version it ships in. A
  test reflects each Protocol's method names and fails when a method exists in a
  Protocol but not in the manifest.
- **`plugin`** - generated per plugin from its declarations
  ([decision-26](decision-26%20-%20Derive-the-bridge-allowlist-and-the-generated-client-from-one-declared-manifest.md)),
  checked into that plugin's frontend.

Composition: `createBridgeClient(transport, {plugin, grants})` returns one
object with `host.*` and `plugin.*`, both feeding the same dispatcher.

Rules that come with it:

- **Canonical grants, not namespace booleans.** `layers.read`, `layers.write`,
  `settings.read`, `notifications.info`, `styles.apply`. A namespace-wide flag
  turns every future method into an automatic grant.
- **Handles, not paths.** No page-supplied filesystem path. `open_vector` is
  deferred until TASK-20 can mint a host-side `FileRef`; the generated types
  brand refs so a `StyleRef` cannot be passed where a `LayerRef` is expected,
  and the host re-checks ownership against the view binding.
- **Result unions for expected failures.** Generated `tryX` variants return
  `{ok: true, value} | {ok: false, code}` with the code union derived from
  `BridgeErrorCode`, alongside the throwing form.
- **Paging for anything unbounded.** `list`/`selection` take `{limit, cursor}`
  and return `{items, next_cursor?, truncated}`; an unbounded array across
  `QWebChannel` is a freeze.
- **Stream-first for anything slow.** Algorithms and jobs are subscriptions with
  coalesced progress, not invocations that outlive the client's timeout.
- **Declared thread affinity.** Each generated method states `gui` or `worker`;
  the client serialises GUI-affine calls per view.
- **Feature detection at handshake.** The handshake advertises the granted
  operation ids and a `host_schema_version`; unknown operations are refused
  there, not on the first click.

**First slice (read-only, non-destructive):** `layers.list`, `layers.get`,
`project.layer_ids`, `settings.get`, `notifications.info`, `styles.apply`.
Deferred to their owners: `layers.open_vector` (TASK-20), `project.add_layer` and
`settings.set` (mutations), `algorithms.execute` (TASK-15/TASK-14 job surface),
and unpaged selections.

## Consequences

- The bridge package gains a public host surface, which is a real API commitment
  for `0.x`: `host_schema_version` plus additive-only changes are what make it
  survivable, and a breaking rename needs the contract version bumped.
- Every exposure widens the attack surface. The Protocols are the right
  boundary, but each operation still needs authorization, input validation
  (decision-26) and attribution to the calling view.
- A read-only first slice is enough for a real panel and can ship before
  TASK-20; the risky operations arrive with the authority they need instead of
  being bolted on later.
- Deferring `algorithms.execute` means the first host surface cannot start work
  of its own; a frontend that needs that uses a plugin-declared action until the
  job surface lands.

## Amendment: what the first slice settled (2026-10-24)

The read-only surface above is implemented and is now the acceptance criterion
for anything added to it. Where this document was open, the implementation chose:

- **The manifest is code, next to the Protocols.** `qgis_sdk.bridge.host` carries
  `HOST_OPERATIONS` - six entries for the first slice - each with a canonical
  grant, a `gui` affinity and the Protocol method it wraps. Every method of the
  five curated Protocols *and* `Algorithms` is either an entry or lives in
  `DEFERRED_HOST_METHODS` with the reason and the owning task, and a test
  reflects the Protocols so a new method cannot appear unaccounted for.
- **Paging is one shape for every list.** `{limit?, cursor?}` in,
  `{items, truncated, next_cursor?}` out. The cursor is an offset encoded as a
  decimal string with a declared `pattern` (`[0-9]+`), so "the host issued it" is
  a check rather than a promise: a malformed cursor is refused as
  `invalid_payload` instead of being read as the first page. `limit` defaults to
  50 and is capped at 200, and both the pattern and the cap are enforced on both
  sides - the request schema refuses them and the generated client refuses them
  before the transport.
- **Public types are named by the manifest.** `layers.get` declares
  `VectorLayerInfo` and `layers.list` reuses the same schema object, so a page
  gets one interface rather than a structural copy per operation.
- **Two surfaces, two sets of identifiers.** The host module exports
  `createHost`, `HostOperations`, `HostContractError`, `HOST_OPERATIONS`,
  `HOST_FINGERPRINT`, `HOST_SCHEMA_VERSION`; a plugin module keeps
  `createOperations`, `PluginOperations`, `ContractError`, `OPERATIONS`. They
  share the renderer and no names, so one page can import both.
- **Version and advertisement.** `HOST_SCHEMA_VERSION = 1` is exported by the
  generated module and sent in the handshake next to the registered operation
  ids; `BRIDGE_PROTOCOL_VERSION` is untouched because the envelope did not
  change.

Still deferred from the rules above, and not claimed by the slice: generated
`tryX` result unions (the throwing form ships first), branded `FileRef` /
`StyleRef` handles (they arrive with TASK-20), the `createBridgeClient`
composition, client-side serialisation of GUI-affine calls, and advertising
*grants* rather than ids in the handshake.

## Second slice, 2026-10-25 (TASK-20)

`layers.open_vector` leaves the deferred list: it takes a `FileRef` the host
minted (`HostAuthority.grant_file` from a picker result or a plugin grant) and
the host resolves the ref against the calling binding on every call, exactly as
the rules above asked. Two operations arrive with it: `files.export(FileRef,
content)` writes through a `write` ref, and the `network.fetch` stream answers
one request through the view's `NetworkGrant` over the TASK-5 transport. The
generated module exports `FileRef` and `HttpHeader` under their titles; the
`StyleRef` brand, `tryX` unions and advertised grants stay deferred.

## Status review, 2026-11-06 (TASK-87, TASK-88)

Five sprints later the surface is **59 operations - 54 calls and 5 streams -
behind 19 canonical grants**, and the rules above still decide each one. What
this review adds is the accounting: what the growth settled, what it changed
about the rules, and what is still open from the second slice.

What holds, unchanged:

- **The inventory is declared, never inferred.** Every operation is a
  `HostOperation` in `qgis_sdk.bridge.host` with a canonical grant, a `gui`
  affinity and the Protocol method it wraps, and the reflection test still fails
  when a Protocol method is neither an operation nor an entry in
  `DEFERRED_HOST_METHODS`. Ten methods are deferred today, each with its reason
  and owner: the two unpaged/unbounded reads (`Layers.selection`,
  `Layers.export_vector`), the two filesystem-destination calls a page may not
  make (`Rasters.export_raster`, `Layers.export_vector`), the mutation the
  protocol does not have yet (`Settings.set`), four notification levels and a
  button, and the plugin-local `Algorithms.execute`.
- **Handles, not paths.** Every operation a page can reach that touches a file
  takes a `FileRef` the host minted: `layers.open_vector`, `rasters.open`,
  `files.export`, `project.read`, `project.write`. `project.save` names no path
  at all.
- **Paging for what a project cannot bound.** `layers.list`, `algorithms.list`
  and `features.page` page; variables, custom properties and bookmarks are
  answered whole, because a project file bounds them and a page that had to loop
  would call four times to draw one panel.
- **Stream-first for what is slow or unbounded.** Four of the five streams
  arrived with the services that needed them: `features.page` (one page per
  frame), `canvas.extent_changed`, `canvas.capture` (one frame, then complete)
  and `project.changed` (one frame per change, never completing).
  `algorithms.run` stayed a call: the four-operation Processing slice runs one
  algorithm and answers its outputs, and progress over it is still the deferred
  job surface.
- **Additive wire, bumped only when it has to be.** `HOST_SCHEMA_VERSION` is
  still 1 and `BRIDGE_PROTOCOL_VERSION` still 2. `HOST_FINGERPRINT` moved once
  per slice, which is what a frontend compares; titles, handler names and the
  display-only annotations below stay out of it, so a rewording does not
  invalidate a client.

What this sprint added to the rules:

- **One annotation, declared beside the operation.** `HostOperation.destructive`
  was open in point 2 and is now a field: seven operations carry it
  (`project.read`, `project.write`, `project.save`, `project.remove_layer`,
  `project.remove_bookmark`, `project.unset_variable`,
  `project.unset_property`), it crosses in the manifest, and a test pins the list
  so an operation cannot become destructive by accident or stay quiet on purpose.
  The agent consent list (decision-49 point 4) and `AGENT001` read this field;
  nothing infers it from a name.
- **One kind, three faces.** `LayerParameter(kind=...)` narrows the native
  picker, the Processing parameter and the wire (`layer_kind`), so "a raster
  input" is one declaration rather than three spellings that can drift. A layer
  input that names no kind is still vectors-only, which is what every
  declaration written before this sprint means.
- **Two models, one union.** `layers.get` answers `VectorLayerInfo |
  RasterLayerInfo` discriminated by `kind`, instead of one object with the
  union of both shapes; the generated TypeScript narrows with a single
  comparison.

Still deferred from the earlier amendments, and none of it is claimed by the
growth: generated `tryX` result unions (the throwing form ships), a branded
`StyleRef`, the `createBridgeClient` composition, client-side serialisation of
GUI-affine calls (every operation is `gui`; a caller still serialises itself),
and advertising *grants* rather than operation ids in the handshake.

The consequence for the next slice is the one this document opened with: the
surface is now wide enough that "expose the Protocol" is no longer the question
- layouts, the remaining layer kinds and the connection service each land as
their own declared operations, with their own grants, and the deferred list is
where a reader finds out why the ones that did not are absent.
