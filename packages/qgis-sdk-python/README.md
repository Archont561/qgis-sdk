# qgis-sdk

**The next-generation Python SDK for effortless QGIS plugin authoring.**

Turn Python actions into QGIS plugins with less boilerplate. Test plugin logic
without QGIS, build native and web interfaces over the same actions, and ship
an installable ZIP. This developer kit brings together the
[`qgis-sdk-runtime`](https://pypi.org/project/qgis-sdk-runtime/) and
[`qgis-sdk-tools`](https://pypi.org/project/qgis-sdk-tools/) at matching versions.

> Status: `0.8.0`, experimental `0.x`. Each `0.Y.0` carries migration
> notes; nothing is promised stable before `1.0.0`.

## Installation

```sh
pip install qgis-sdk                            # runtime + tools
pixi add --channel https://prefix.dev/archont561/archont561 qgis-sdk
```

## Example

```python
from qgis_sdk import QgisSdkPlugin
from qgis_sdk.core import PluginContext
from qgis_sdk.models import LayerInput, Metres, VectorLayerInfo
from qgis_sdk.ui import Button, Dialog, Form, LayerPicker, Number, on


app = QgisSdkPlugin(id="field.tools", title="Field tools")

@app.surface
class BufferDialog(Dialog):
    title = "Buffer"
    layer_id = LayerPicker(kind="vector", required=True)
    distance = Number(range=(0, 10_000), required=True)
    form = Form([layer_id, distance], action_id="buffer")
    run = Button(text="Run")

    @on(run).clicked
    def run_clicked(self) -> None:
        self.ctx.log.info("buffered", layer=self.form.submit().id)


@app.action(id="buffer", title="Buffer")
def buffer(ctx: PluginContext, layer_id: LayerInput, distance: Metres) -> VectorLayerInfo:
    params = {"INPUT": layer_id, "DISTANCE": distance}
    return ctx.algorithms.run("native:buffer", params).vector("OUTPUT")
```

`qgis-sdk new <directory>` writes a project on this API; `check`, `test`,
`dev` and `build` take it from there. What QGIS's loader needs -
`metadata.txt`, the `classFactory` - is rendered by `build` and `dev`,
never written into the project.

## Documentation

- [Python package guide](https://archont561.github.io/qgis-sdk/python/) -
  declarations, the UI catalogue, services, Processing, the bridge host
  side, the scaffold, the command, release and migration notes.
- [TypeScript SDK](https://www.npmjs.com/package/@archont561/qgis-sdk) and
  [web components](https://github.com/Archont561/qgis-sdk/tree/main/packages/qgis-sdk-ui) -
  the page side of a `QWebEngineView` interface.
- [Workspace, harnesses and qualification evidence](https://archont561.github.io/qgis-sdk/contributing/workspace/).

## License

MIT
