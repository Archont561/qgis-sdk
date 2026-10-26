---
id: decision-48
title: Give the QGIS Python console the curated services and plugin handles, never iface
date: '2026-10-26'
status: accepted
---
## Context

Asked on 2026-10-26: is the qgis-sdk API available from the QGIS Python
console, and how should an API "around `iface`" be exposed there? Today the
console reaches a running plugin only through
`qgis.utils.plugins[name].runtime` - a `PluginRuntime` whose `actions`,
`streams`, `description` and `instance` are documented "for advanced adapters
and tests" - and reaches the runtime modules only through the plugin-private
vendored path (`<plugin>._vendor.qgis_sdk`) or, under `qgis-sdk dev`, through
the `PYTHONPATH` the dev session sets. There is no console-facing surface, and
`iface` itself is kept opaque everywhere (decision-9: never serialise or expose
it; `ctx.desktop` wraps it as `IfaceDesktopAccess`).

The runtime already has the builder a console needs:
`qgis_sdk.adapters.qgis.context.native_plugin_context(scope, settings_prefix=,
iface=)` assembles the same `PluginContext` a Desktop plugin gets - `layers`,
`project`, `settings`, `styles`, `algorithms`, `network`, `notifications`,
`desktop` - over a `ResourceScope`.

## Decision

1. **The console gets the same curated surface as a plugin, not `iface`.**
   `qgis_sdk.console.connect(*, iface=None, settings_prefix="console",
   notifications=None) -> ConsoleSession` builds a `PluginContext` through
   `native_plugin_context` over `qgis.utils.iface` (or the `iface` passed,
   or none in a standalone `QgsApplication`, where `ctx.desktop` refuses by
   name). `session.ctx` is that context; its services are the Protocols the
   bridge host surface wraps (decision-27), so what a page may be granted,
   a handler receives and the console can call are one API. `iface` stays
   behind `ctx.desktop` as today; the SDK adds no wrapper that re-exposes
   `QgisInterface` methods one by one.
2. **Plugin handles.** `session.plugin(name) -> PluginHandle` wraps
   `qgis.utils.plugins[name].runtime`: `description`, `actions`, `streams`,
   `algorithms` (the Processing ids the plugin registered, new on
   `PluginRuntime`), `state`, `run(action_id, **inputs)` (validated like a
   bridge call, returns the result or raises the same `QgisSdk` error),
   `open(action_id)` (the declared form or surface of decision-45/46, GUI
   thread), `reload()` under a dev session only. A plugin built by another
   SDK version is still a `PluginRuntime` behind the adapter, so the handle
   works across vendored copies as long as the attribute set is stable;
   attributes it lacks refuse by name (decision-39).
3. **Reachable without knowing the import path.** `DesktopLifecycleAdapter`
   gains `console() -> ConsoleSession` bound to *that plugin's* context (the
   same service instances the plugin uses, so console and plugin read one
   project and one settings prefix). So `plugins["simple"].console()` works
   for an installed, vendored plugin and `qgis_sdk.console.connect()` works
   under `qgis-sdk dev` or any environment where the runtime is importable.
   Nothing is installed into QGIS's Python to make either work.
4. **Ownership.** A session owns a `ResourceScope`; `session.close()` (or
   `with connect() as s:`) disposes subscriptions, temporary outputs and
   jobs it started; a plugin-bound session closes with the plugin's unload.
   Sessions never own project layers (decision-21 borrowing rules apply).
5. **Not included.** No REPL magic, no auto-import into the console
   namespace, no `eval` of plugin code, no `iface` proxy objects. `qgis-sdk
   dev` may print the two-line recipe when it starts.

## Consequences

- The console becomes the third client of one surface (page, handler,
  console); `host()` of decision-43 needs no change because
  `DesktopLifecycleAdapter` is what `classFactory` already returns.
- `PluginRuntime.algorithms` is additive. `ConsoleSession` and
  `PluginHandle` are new public runtime API, documented in doc-12 with the
  console recipe; shipped in 0.7.0.
- Scheduled as TASK-73 in m-6 (after TASK-63 for provider ids and TASK-64
  for the generated adapter path).
