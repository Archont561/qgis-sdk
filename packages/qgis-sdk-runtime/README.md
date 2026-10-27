# qgis-sdk-runtime

**What a qgis-sdk plugin imports inside QGIS: declarations, the UI
catalogue, the services and the adapters - standard library only.**

Plain classes carry the plugin: `@plugin` and `@action` declare it, a
`Dialog` or `Dock` declares its native window from the catalogue, `ctx`
reaches layers, Processing, files, settings, network, the log and the
WebEngine bridge host side. `qgis_sdk.adapters.desktop.host()` is the
`classFactory` a built plugin binds, so a project carries the plugin and
nothing of the host. The pure layers import without QGIS or Qt; a plugin
built with `qgis-sdk build` vendors a private copy and installs nothing.

> Status: `0.6.0`, experimental `0.x`. Each `0.Y.0` carries migration
> notes; nothing is promised stable before `1.0.0`.

## Installation

```sh
pip install qgis-sdk-runtime   # the QGIS Python console, a host script, a vendored copy
pip install qgis-sdk           # the developer kit: runtime + tools
```

## Example

```python
from qgis_sdk import action, menu, plugin
from qgis_sdk.ui import Button, Dialog, Form, LogView, Number, on


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


@plugin(id="example", title="Example")
class Example:
    surfaces = (PingDialog,)

    @action(id="ping", title="Ping")
    def ping(self, value: int) -> int:
        return value
```

## Documentation

- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  declarations, the UI catalogue and the declared surface form, services,
  Processing, the bridge host side, release and migration notes.
- [TypeScript SDK](https://www.npmjs.com/package/@archont561/qgis-sdk) and
  [web components](https://github.com/Archont561/qgis-sdk/tree/main/packages/qgis-sdk-ui) -
  the page side of a `QWebEngineView` interface.

## License

MIT
