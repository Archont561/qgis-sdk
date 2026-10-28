---
title: Your first plugin
description: Scaffold a loadable QGIS plugin with qgis-sdk new, check and test it without QGIS, run it from source inside QGIS Desktop, and build the installable ZIP.
sidebar:
  order: 2
---

Five commands take a directory to an installable plugin. Every step after
`new` reads `pyproject.toml`, so there is no `metadata.txt`, `classFactory`
or view module to maintain: `build` and `dev` derive what QGIS needs.

## How do I scaffold a project?

```sh
qgis-sdk new my_tools --title "My Tools"
cd my_tools
```

`new` asks whether you want a web UI (`--web vanilla|react`, or `--no-input`
to skip the question) and writes:

| Path | What it is |
| :-- | :-- |
| `pyproject.toml` | The project *is* the plugin: name, version, `qgis-sdk-runtime` dependency, `[tool.qgis-sdk]` with the plugin application, placement and grants. |
| `my_tools/plugin.py` | A `QgisSdkPlugin` with action functions and a typed context. |
| `my_tools/ui.py` | With `--ui native`, a `Dialog` declared from the UI catalogue. |
| `tests/` | pytest on the SDK fakes; runs without QGIS. |
| `web/` | Only with `--web`: a Vite page on `@archont561/qgis-sdk` with the generated `bridge.schema.ts`. |

## What does the plugin look like?

```python
from qgis_sdk import QgisSdkPlugin, menu
from qgis_sdk.core import PluginContext
from qgis_sdk.ui import Button, Dialog, Form, LogView, Number, on


app = QgisSdkPlugin(id="my_tools", title="My Tools")

@app.surface
@menu("Plugins/My Tools")
class PingDialog(Dialog):
    title = "Ping"
    value = Number(integer=True, required=True)
    form = Form([value], action_id="ping")
    ping = Button(text="Ping")
    answers = LogView(label="Answers")

    @on(ping).clicked
    def pinged(self) -> None:
        self.ctx.log.info("pong", value=self.form.submit())


@app.action(id="ping", title="Ping")
def ping(ctx: PluginContext, value: int) -> int:
    return value
```

The decorator keeps the original function. The host injects `ctx` during
execution; tests can call the function directly with a fake `PluginContext`.

## How do I check and test it without QGIS?

```sh
qgis-sdk check    # pyproject, syntax, imports, UI rules, runtime version
qgis-sdk test     # pytest on the SDK fakes
```

`check` reports what would stop the project from loading in QGIS, each
finding with a rule id. `test` needs no QGIS; add `--target qgis` for the
native layers on a headless QGIS, or `--target desktop` for the full Desktop
lifecycle when one is installed.

## How do I run it inside QGIS?

```sh
qgis-sdk dev
```

A real QGIS Desktop starts with the project loaded from source and reloads
it on save. With a web page, Vite runs alongside with hot module reload.

## How do I build the ZIP?

```sh
qgis-sdk build    # dist/my_tools-<version>.zip
```

The ZIP carries the plugin, a private copy of `qgis-sdk-runtime` and the
rendered `metadata.txt` and `classFactory`. Install it through QGIS's plugin
manager like any other plugin; nothing else is installed on that machine.

## Where next

- [Declarations](/qgis-sdk/python/declarations/) - application and action registration.
- [Desktop bindings and native surfaces](/qgis-sdk/python/desktop-bindings-and-native-surfaces/) -
  the UI catalogue, `Dialog` and `Dock`, `@on`, forms.
- [Project scaffold](/qgis-sdk/python/project-scaffold/) - every file `new`
  writes and every flag it takes.
- [The schema module and `QgisSdk`](/qgis-sdk/typescript/the-schema-module-and-qgissdk/) -
  the page side of a web UI.
