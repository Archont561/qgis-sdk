---
title: Your first plugin
description: Scaffold a plugin, then follow one typed action from a pure test to native and web interfaces.
sidebar:
  order: 2
---

QGIS SDK targets **QGIS 4** and is experimental. You can write and test a
plugin without QGIS; running it in Desktop requires a supported QGIS
installation and display. See [supported targets](/qgis-sdk/python/supported-targets/).

## Scaffold a project

```sh
qgis-sdk new my_tools --title "My Tools" --no-input
cd my_tools
```

The default is a Python-only plugin. To add a native dialog, run this
**instead** of the first `new` command:

```sh
qgis-sdk new my_tools --title "My Tools" --ui native --no-input
```

The files include:

| Path | Purpose |
| :-- | :-- |
| `pyproject.toml` | Project metadata and the `module:app` plugin entry. |
| `my_tools/plugin.py` | `QgisSdkPlugin` and its actions. |
| `tests/test_plugin.py` | A QGIS-free test using SDK fakes. |
| `my_tools/ui.py` | Added only with `--ui native`; the default has no native UI module. |
| `web/` | Added only with `--web`; contains the page and generated `bridge.schema.ts`. |

For a web page, use this instead and install the page dependencies separately:

```sh
qgis-sdk new my_tools --title "My Tools" --web vanilla --no-input --no-install
```

`--web vanilla` and `--web react` scaffold pages. Vue and Svelte have SDK
adapters, but are not scaffold choices. See the
[scaffold reference](/qgis-sdk/python/project-scaffold/) for the options.

## One action, three paths

The repository's [Simple reference plugin](https://github.com/Archont561/qgis-sdk/tree/main/examples/simple)
has both a native dialog and a web page. These excerpts are from that working
project; they use the **same** `buffer` action. Its host injects `ctx`, while
the caller supplies a layer, distance and projected CRS.

### Declare it

In `simple/plugin.py`, the action delegates to the plugin's workflow:

<!-- source: examples/simple/simple/plugin.py -->
```python
@app.action(id="buffer", title="Buffer in a projected CRS")
def buffer(
    ctx: PluginContext,
    layer_id: LayerInput,
    distance_metres: Metres,
    working_crs: CrsInput,
) -> VectorLayerInfo:
    """Buffer a layer by metres inside ``working_crs``; style and present it."""
    return LocalGisWorkflow(ctx).buffer(layer_id, distance_metres, working_crs)
```

### Test it without QGIS

The real test calls the registered action using fake services; the fake host
supplies the source fixture and `WORKING_CRS`:

<!-- source: examples/simple/tests/test_workflow_pure.py -->
```python
def test_buffer_creates_a_styled_new_layer_and_keeps_the_source(
    fake_host: FakeHost,
) -> None:
    source = fake_host.runtime.actions["open_fixture"]()

    output = fake_host.runtime.actions["buffer"](source.id, 500.0, WORKING_CRS)

    assert output.id != source.id
    assert output.geometry_type == "polygon"
    assert fake_host.styles.applied(output.id) == (LocalGisWorkflow.OUTPUT_STYLE,)
    assert fake_host.project.layer_ids() == (source.id, output.id)
    assert fake_host.layers.layer(source.id) == source
```

### Open a native form

The reference plugin registers `BufferDialog` as a surface. Its form derives
fields from the action's schema; clicking the button submits that action:

<!-- source: examples/simple/simple/surfaces.py -->
```python
    def build(self) -> Column:
        self.form = Form.for_action(self.ctx, "buffer", initial=self.initial)
        return Column("buffer_dialog", [self.form, Button("run", "Buffer")])

    @on("run").clicked
    def run(self) -> None:
        """Submit the form; a refusal becomes a warning, a result closes the window."""
        try:
            output = self.form.submit()
        except QgisSdkError as error:
            self.ctx.notifications.warning(str(error))
            return
        self.ctx.log.info("buffered", layer=output.name, crs=output.crs or "")
        self.ctx.notifications.success(f"Buffered into {output.name}")
        self.ctx.view.request_close()
```

### Call it from a web page

The generated `bridge.schema.ts` gives the page a typed `qgis.buffer` method.
`web/src/main.ts` creates `qgis` with `QgisSdk.fromBridgeSchema(schema)`;
`web/src/app.ts` calls it with the same inputs:

<!-- source: examples/simple/web/src/app.ts -->
```ts
	run("buffer", async () => {
		const output = await qgis.buffer({
			layer_id: required(state.sourceId, "open the dataset first"),
			distance_metres: Number(input(root, "distance").value),
			working_crs: input(root, "crs").value,
		});
		state.outputId = output.id;
		element(root, "buffer-result").textContent =
			`${output.name} (${output.geometry_type}, ${output.crs ?? "no CRS"})`;
	});
```

The page test uses a scripted bridge, not a live QGIS host. The full reference
project includes tests and instructions for both fake and native execution.

## Check, test and run your scaffold

From the `my_tools` directory:

```sh
qgis-sdk check
qgis-sdk test
qgis-sdk dev
qgis-sdk build
```

`check` validates the project; `test` runs the pure tests without QGIS.
`qgis-sdk test --target qgis` needs QGIS for native tests, while
`--target desktop` and `dev` need a Desktop installation. `dev` opens the
plugin from source; `build` makes `dist/my_tools-<version>.zip` with the
runtime and generated QGIS entry point. Install the ZIP via QGIS's plugin
manager. A web project also needs its JavaScript dependencies installed.

## Where next

- [Declarations](/qgis-sdk/python/declarations/) and [native surfaces](/qgis-sdk/python/desktop-bindings-and-native-surfaces/).
- [The schema module and `QgisSdk`](/qgis-sdk/typescript/the-schema-module-and-qgissdk/).
- [Testing a plugin](/qgis-sdk/guides/test-a-plugin/) and the [reference plugin](https://github.com/Archont561/qgis-sdk/tree/main/examples/simple).
