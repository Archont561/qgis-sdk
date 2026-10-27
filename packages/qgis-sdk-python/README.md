# qgis-sdk

**The Python developer kit for QGIS plugins: the runtime a plugin imports
and the command that scaffolds, checks, tests, runs and builds it.**

Declare a plugin on plain classes and let the SDK derive the rest: the JSON
description a web view reads, the native windows, the Processing algorithms,
the bridge allowlist and the typed TypeScript client. The pure layers import
without QGIS or Qt, so a plugin is testable from source. `qgis-sdk` is a
code-free kit that installs [`qgis-sdk-runtime`](../qgis-sdk-runtime) and
[`qgis-sdk-tools`](../qgis-sdk-tools) at matching versions.

> Status: `0.6.0`, experimental `0.x`. Each `0.Y.0` carries migration
> notes; nothing is promised stable before `1.0.0`.

## Installation

```sh
pip install qgis-sdk                            # runtime + tools
pip install "qgis-sdk[controlled-deployment]"   # optional Pydantic adapter
pixi add --channel https://prefix.dev/archont561/archont561 qgis-sdk
```

## Example

```python
from qgis_sdk import action, plugin
from qgis_sdk.models import LayerInput, Metres, VectorLayerInfo
from qgis_sdk.ui import Button, Dialog, Form, LayerPicker, Number, on


class BufferDialog(Dialog):
    title = "Buffer"
    layer_id = LayerPicker(kind="vector", required=True)
    distance = Number(range=(0, 10_000), required=True)
    form = Form([layer_id, distance], action_id="buffer")
    run = Button(text="Run")

    @on(run).clicked
    def run_clicked(self) -> None:
        self.ctx.log.info("buffered", layer=self.form.submit().id)


@plugin(id="field.tools", title="Field tools")
class FieldTools:
    surfaces = (BufferDialog,)

    @action(id="buffer", title="Buffer")
    def buffer(self, layer_id: LayerInput, distance: Metres) -> VectorLayerInfo:
        params = {"INPUT": layer_id, "DISTANCE": distance}
        return self.ctx.algorithms.run("native:buffer", params).vector("OUTPUT")
```

`qgis-sdk new <directory>` writes a project on this API; `check`, `test`,
`dev` and `build` take it from there. What QGIS's loader needs -
`metadata.txt`, the `classFactory` - is rendered by `build` and `dev`,
never written into the project.

## Documentation

- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  declarations, the UI catalogue, services, Processing, the bridge host
  side, the scaffold, the command, release and migration notes.
- [TypeScript SDK](https://www.npmjs.com/package/@archont561/qgis-sdk) and
  [web components](https://github.com/Archont561/qgis-sdk/tree/main/packages/qgis-sdk-ui) -
  the page side of a `QWebEngineView` interface.
- [Workspace, harnesses and qualification evidence](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md).

## License

MIT
