---
title: Concepts and vocabulary
description: The handful of words the QGIS SDK uses everywhere - plugin, action, surface, ctx, services, grants, bridge, scope - defined once, with where each is documented.
sidebar:
  order: 3
---

One declaration drives every host: the same plugin object describes the
plugin to QGIS, to the test fakes and to a web page. These are the terms the
guides rely on.

## Plugin and action

A **plugin** is a `QgisSdkPlugin(id=..., title=...)`. An **action** is a function
registered with `@app.action(id=..., title=...)`: a named, typed operation
whose first argument is an injected `PluginContext`. Actions are headless; they know
nothing about buttons or pages. Everything a user can trigger - a toolbar
button, a native form, a web page call, a Processing algorithm - ends in an
action. See [Declarations](/qgis-sdk/python/declarations/).

## Parameter kinds

An action's parameters carry marker types - `LayerInput`, `Metres`,
`CrsInput`, `FileInput`, `FieldInput`, `Range`, choices - and each kind is
complete across hosts: a Qt widget in a native form, a Processing parameter,
a JSON-schema annotation a page reads, a fake in tests. A kind every host
cannot render is not added. See
[Forms: an action's inputs as a window](/qgis-sdk/python/forms-an-actions-inputs-as-a-window/).

## Surfaces

A **surface** is a native window: a `Dialog` or `Dock` subclass declaring its
widgets from the UI catalogue (`Number`, `LayerPicker`, `Form`, `Button`,
`LogView`, ...), or a pure-PyQt `build()`, or a `.ui` file. A plugin lists
its surfaces in `surfaces = (...)`; `@toolbar` and `@menu` on an action or a
surface place it in QGIS. Surfaces never import `qgis.PyQt` themselves. See
[Desktop bindings and native surfaces](/qgis-sdk/python/desktop-bindings-and-native-surfaces/).

## `ctx` and the services

`ctx` is the runtime-bound context on the plugin class and on every surface
instance. Its **services** - `layers`, `project`, `algorithms`, `files`,
`settings`, `network`, `log`, `jobs`, `ui`, `actions` - are the only way
plugin code reaches QGIS; `iface` is never exposed. Each service has a fake,
so a plugin is tested without QGIS. See
[Scoped plugin runtime](/qgis-sdk/python/scoped-plugin-runtime/) and
[Scoped jobs](/qgis-sdk/python/scoped-jobs/).

## Processing and providers

`ctx.algorithms` lists, describes and runs any registered algorithm with
typed parameters and returns owned outputs. A plugin's own algorithms are
provider or function algorithms listed in `providers = [...]`, written once
and shown in the Processing toolbox. See
[Processing algorithms and safe outputs](/qgis-sdk/python/processing-algorithms-and-safe-outputs/)
and [Providers](/qgis-sdk/python/providers-algorithms-in-the-qgis-processing-toolbox/).

## Web view, bridge, grants

A **web view** is a `QWebEngineView` page the plugin opens as a dialog or
dock. The **bridge** connects it to the plugin over an allowlist: the page
may call the plugin's actions and the host namespaces its **grants** name
(`layers.read`, `algorithms.run`, ...). `qgis-sdk bridge generate` renders
the schema module; `QgisSdk.fromBridgeSchema(schema)` is the typed client.
See [WebEngine bridge, host side](/qgis-sdk/python/webengine-bridge-host-side/)
and [The schema module and `QgisSdk`](/qgis-sdk/typescript/the-schema-module-and-qgissdk/).

## Scope

Everything a plugin acquires - layers it added, jobs it started, files it
opened, signals it connected - belongs to a **scope** the runtime closes on
unload, so a plugin can be unloaded and reloaded without leaking into QGIS.
See [Scoped plugin runtime](/qgis-sdk/python/scoped-plugin-runtime/).

## Where the words are defined in full

- [Python package guide](/qgis-sdk/python/) - the host and plugin side.
- [TypeScript SDK guide](/qgis-sdk/typescript/) - the page side.
- [Design decisions](/qgis-sdk/reference/design-decisions/) - why each
  surface is shaped the way it is.
