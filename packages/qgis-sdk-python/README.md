# qgis-sdk

**The Python developer kit for QGIS plugins: runtime plus tools.**

Declare a plugin on plain classes and let the SDK derive the rest: the JSON
description a web view reads, the native dialogs, the Processing algorithms, the
bridge allowlist and the generated TypeScript client. The pure layers import
without QGIS or Qt, so a plugin is testable from source. `qgis-sdk` is a
code-free kit that installs [`qgis-sdk-runtime`](../qgis-sdk-runtime) (what a
plugin imports) and [`qgis-sdk-tools`](../qgis-sdk-tools) (the command) at
matching versions.

> Experimental `0.x`. Each `0.Y.0` carries migration notes; nothing is
> promised stable before `1.0.0`.

## Installation

```sh
pip install qgis-sdk                            # runtime + tools
pip install "qgis-sdk[controlled-deployment]"   # optional Pydantic adapter
pip install qgis-sdk-runtime                    # the runtime alone (QGIS console)
pixi add --channel https://prefix.dev/archont561/archont561 qgis-sdk
```

## Example

```python
from dataclasses import dataclass

from qgis_sdk import action, describe_plugin, plugin


@dataclass
class RunRequest:
    count: int
    label: str | None = None


@plugin(id="example.tools", title="Example tools")
class Tools:
    @action(id="run", title="Run")
    def run(self, request: RunRequest) -> int:
        return request.count


print(describe_plugin(Tools).to_json())
```

`qgis-sdk new <directory>` writes a plugin project built on the same API:
`pyproject.toml` naming the class under `[tool.qgis-sdk]`, the package with
`plugin.py`, a starter test and an optional Vite web UI (`--web
vanilla|react|svelte|vue`). What QGIS's loader needs - `metadata.txt`, the
`classFactory` - is rendered by `build` and `dev`, never written into the
project. `qgis-sdk check` reports what would stop it from loading in QGIS or
from being tested without it. `qgis-sdk test` runs the project's pytest QGIS-free by default
(`--target qgis|desktop` for the native layers, arguments pass through) and
`qgis-sdk dev` starts the plugin from source in a real QGIS Desktop with an
isolated profile, reload on save and, for a web UI, Vite with hot module
replacement. `qgis-sdk build` checks the project and writes an installable
ZIP with the runtime vendored inside, so the plugin needs nothing installed.

## Documentation

- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  declarations, runtime, adapters, forms, algorithms, the bridge host side,
  the scaffold, release and migration notes.
- [TypeScript bridge](https://www.npmjs.com/package/@archont561/qgis-sdk) -
  the companion package for a `QWebEngineView` interface.
- [Workspace, harnesses and qualification evidence](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md).

## License

MIT
