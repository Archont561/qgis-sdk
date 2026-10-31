# qgis-sdk-runtime

**The runtime that brings your Python plugin to life in QGIS.**

Declare actions and native surfaces with plain Python, then reach QGIS
capabilities through scoped services. Pure layers import without QGIS or Qt;
`qgis-sdk build` vendors a private runtime into the plugin ZIP. The runtime
has no third-party Python dependencies; QGIS and Qt are supplied by the host.

> Status: `0.9.0`, experimental `0.x`. Each `0.Y.0` carries migration
> notes; nothing is promised stable before `1.0.0`.

## Installation

```sh
pip install qgis-sdk-runtime   # the QGIS Python console, a host script, a vendored copy
pip install qgis-sdk           # the developer kit: runtime + tools
```

## Example

```python
from qgis_sdk import QgisSdkPlugin, menu
from qgis_sdk.core import PluginContext
from qgis_sdk.ui import Button, Dialog, Form, LogView, Number, on


app = QgisSdkPlugin(id="example", title="Example")

@app.surface
@menu("Plugins/Example")
class PingDialog(Dialog):
    title = "Ping"
    value = Number(integer=True, required=True)   # objectName form/value
    form = Form([value], action_id="ping")        # submits through ctx.actions
    ping = Button(text="Ping")                    # objectName buttons/ping
    answers = LogView(label="Answers")            # shows ctx.log as it arrives

    @on(ping).clicked
    def pinged(self) -> None:
        self.ctx.log.info("pong", value=self.form.submit())


@app.action(id="ping", title="Ping")
def ping(ctx: PluginContext, value: int) -> int:
    return value
```

## Documentation

- [Python package guide](https://archont561.github.io/qgis-sdk/python/) -
  declarations, the UI catalogue and the declared surface form, services,
  Processing, the bridge host side, release and migration notes.
- [TypeScript SDK](https://www.npmjs.com/package/@archont561/qgis-sdk) and
  [web components](https://github.com/Archont561/qgis-sdk/tree/main/packages/qgis-sdk-ui) -
  the page side of a `QWebEngineView` interface.

## License

MIT
