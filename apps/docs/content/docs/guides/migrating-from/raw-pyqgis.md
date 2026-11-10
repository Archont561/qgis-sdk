---
title: Migrating a raw PyQGIS plugin
description: Take a plugin written directly against iface, QgsProject and QgsProcessingProvider and move it onto the SDK's declarations - about an hour for a medium plugin.
---

This page is for a plugin with no framework at all: a `classFactory`, an `initGui`
that builds `QAction`s, handlers that read `QgsProject.instance()`, and a
`QgsProcessingProvider` subclass. The SDK does not take that code away; it takes
the plumbing around it.

## What maps to what

| Raw PyQGIS | SDK equivalent |
| :-- | :-- |
| `classFactory(iface)` returning a `QgisPlugin` | `QgisSdkPlugin(id=..., title=...)` in `<name>/plugin.py`; `qgis-sdk build` generates the entry point |
| `initGui` / `unload` | `@app.surface`, `@toolbar`, `@menu`, `@shortcut`; teardown through `ctx.scope` |
| `QAction` created and `connect`ed by hand | `@app.action(id=..., title=...)` |
| `iface.messageBar().pushMessage(...)` | `ctx.notifications.warning(...)`, `ctx.notifications.success(...)` |
| `QgsProject.instance()` and its layer registry | `ctx.project`, `ctx.layers` |
| `QgsProcessingProvider` subclass with `loadAlgorithms`, and `QgsProcessingAlgorithm` subclasses | `Provider` plus `@provider.algorithm` on plain functions |
| `iface.activeLayer()` | the layer id an action takes as an input |
| `metadata.txt` written and versioned by hand | rendered from the declaration at build time |
| `QgsApplication` stubs in your tests | `qgis-sdk test`, whose fakes come with the kit |

## Step by step

1. Scaffold beside the old plugin and keep both working while you port:

   ```sh
   qgis-sdk new field_tools --title "Field tools" --no-input
   cd field_tools
   ```

2. Move the plugin class into a declaration, keeping the id it already has, so
   an installed copy keeps its settings:

   ```python
   from qgis_sdk import QgisSdkPlugin

   app = QgisSdkPlugin(id="field_tools", title="Field tools")
   ```

3. Turn each `QAction` handler into an action. The layer becomes an input
   instead of a lookup, so the handler works the same in a test:

   ```python
   @app.action(id="buffer", title="Buffer")
   def buffer(ctx: PluginContext, layer_id: str, distance_metres: float) -> VectorLayerInfo:
       ...
   ```

4. Swap the message bar and the project singleton for the context services:

   ```python
   # before
   iface.messageBar().pushWarning("Field tools", f"buffer failed: {error}")
   layer = QgsProject.instance().mapLayer(layer_id)

   # after
   ctx.notifications.warning(f"buffer failed: {error}")
   layer = ctx.layers.layer(layer_id)
   ```

5. Move the Processing algorithms from class methods to decorated functions
   (decision-42); `describe_algorithm` and the Processing description come from
   the signature and the docstring:

   ```python
   from qgis_sdk.providers import Provider

   provider = Provider(id="field_tools", title="Field tools")

   @provider.algorithm(id="buffer_grid", title="Buffer to grid")
   def buffer_grid(ctx: AlgorithmContext, layer_id: str, spacing: float) -> str:
       """Buffer a layer and snap the result to a grid."""
   ```

6. Run the gates, then delete the hand-written `metadata.txt`, the `QAction`
   wiring and the test stubs:

   ```sh
   qgis-sdk check
   qgis-sdk test
   qgis-sdk dev
   qgis-sdk build       # dist/field_tools-<version>.zip
   ```

## Before and after

```python
# before: __init__.py, one module doing everything
class FieldTools:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):
        self.action = QAction("Buffer", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        if layer is None:
            self.iface.messageBar().pushWarning("Field tools", "select a layer")
            return
        QgsProject.instance().addMapLayer(self._buffer(layer))
```

```python
# after: field_tools/plugin.py, and the toolbar entry is a decorator
app = QgisSdkPlugin(id="field_tools", title="Field tools")

@toolbar(icon="buffer.svg", text="Buffer")
@app.action(id="buffer", title="Buffer")
def buffer(ctx: PluginContext, layer_id: str, distance_metres: float) -> VectorLayerInfo:
    output = LocalGisWorkflow(ctx).buffer(layer_id, distance_metres)
    ctx.notifications.success(f"Buffered into {output.name}")
    return output
```

## Gotchas

- `iface` is never serialised; a handler that needs the host reads `ctx`. That
  is what keeps it testable from source.
- An action that takes inputs cannot run from a toolbar button - give it a
  surface, or `check` reports `UI003`.
- `metadata.txt` becomes build output; a `hasProcessingProvider` line is
  derived from whether the app declares providers.
- A QGIS built without Server refuses the `server` host by name (`HOST003`), so
  a Desktop-only plugin does not silently grow a broken server path.

## Where next

- [Declarations](/python/declarations/) - hosts, bindings and the manifest keys.
- [Processing algorithms and safe outputs](/python/processing-algorithms-and-safe-outputs/) -
  the provider model.
- [Testing a plugin](/guides/test-a-plugin/) - the fakes the pure tests use.
