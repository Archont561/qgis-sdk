---
id: decision-27
title: Expose curated host services to web views as generated namespaces
date: '2026-10-24 21:20'
status: proposed
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
  `qgis_sdk.services`, shipped *inside* `@archont561/qgis-sdk-bridge` and
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
