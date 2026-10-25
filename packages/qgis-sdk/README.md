# qgis-sdk

**Python SDK foundations for QGIS plugins.**

Declare a plugin on plain classes and let the SDK derive the rest: the JSON
description a web view reads, the native dialogs, the Processing algorithms, the
bridge allowlist and the generated TypeScript client. The pure layers import
without QGIS or Qt, so a plugin is testable from source.

> Experimental `0.2.0`. Each `0.Y.0` carries migration notes; nothing is
> promised stable before `1.0.0`.

## Installation

```sh
pip install qgis-sdk
pip install "qgis-sdk[controlled-deployment]"   # optional Pydantic adapter
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

`qgis-sdk new <directory>` writes a loadable plugin project built on the
same API.

## Documentation

- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  declarations, runtime, adapters, forms, algorithms, the bridge host side,
  the scaffold, release and migration notes.
- [TypeScript bridge](https://www.npmjs.com/package/@archont561/qgis-sdk-bridge) -
  the companion package for a `QWebEngineView` interface.
- [Workspace, harnesses and qualification evidence](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md).

## License

MIT
