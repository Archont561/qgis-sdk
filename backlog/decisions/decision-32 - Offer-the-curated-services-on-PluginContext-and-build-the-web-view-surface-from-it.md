---
id: decision-32
title: Offer the curated services on PluginContext and build the web-view surface from it
date: '2026-10-25 17:30'
status: accepted
---
## Context

decision-27 curated five service Protocols (`Layers`, `Project`, `Settings`,
`Styles`, `Notifications`) for web views, reachable through generated host
namespaces. The Python side had the same Protocols in `qgis_sdk.services` and
native adapters for each, but `PluginContext` carried only `notifications`,
`scope`, optional `desktop` and optional `network`: a Python action that wanted
the project had to be handed a service by hand, and nothing tied the instance
it got to the instance the web view's `host.project` was answering from. The
owner asked on 2026-10-25 for the plugin context to have the services, so the
same capability is callable from a web view and from Python.

## Decision

1. **The context carries the curated services.** `PluginContext` gains
   `layers`, `project`, `settings`, `styles`, `algorithms` and `workers` as
   optional fields, each with a `require_<name>()` that refuses by capability
   name and on a closed scope, the pattern `desktop` and `network` already
   followed. A pure or standalone host leaves out what it cannot offer.
2. **One service set, two doors.** `HostServices.from_context(ctx)` builds the
   bridge surface from the context, instance for instance, so a page's
   `layers.list` and a handler's `self.ctx.layers` read one object. It takes
   the transport under the context's network client (`NetworkClient.transport`,
   now public) for `network.fetch` unless told otherwise.
3. **One assembly inside QGIS.** `qgis_sdk.adapters.qgis.native_plugin_context`
   wires every PyQGIS adapter into one context owned by one scope. The scaffold's
   `build_context` calls it when a `QgsApplication` is running and otherwise
   returns a notifications-only context, so a generated project still imports
   and tests without QGIS.
4. **Scope stays the owner.** Nothing here adds a registry or a global: every
   service is built on the plugin's `ResourceScope`, and closing it closes them
   all (decision-6, decision-21).

## Consequences

- Plugin authors reach services through `self.ctx` with typed `require_*`
  accessors; hosts that build their own context are unaffected until they opt
  in field by field.
- The wire surface does not change: the operations, grants and
  `HOST_SCHEMA_VERSION` are untouched; only who supplies the instances moved.
- A later `ctx.jobs` follows the same shape: an optional field on the context,
  bound to the plugin scope, with a `require_jobs()`.

## Amended by decision-39 (2026-10-25)

The `require_<name>()` accessors this record introduced were replaced in the
0.6.0 line by
[decision-39](decision-39%20-%20Expose-optional-services-as-capability-attributes-that-refuse-by-name.md):
each optional service is a capability attribute that refuses by name on read
(`ctx.layers`, `ctx.workers` ...), with `ctx.has(name)` / `ctx.capabilities`
as the probes. Everything else here - the curated services on
`PluginContext`, `HostServices.from_context` wrapping the same instances -
stands.
