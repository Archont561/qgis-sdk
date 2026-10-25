# qgis-sdk-runtime

**What a qgis-sdk plugin imports inside QGIS.**

Declarations on plain classes, the version 1 description contract, the scoped
runtime with its services, local jobs, networking, the WebEngine bridge host
side and the QGIS adapters. Standard library only: a plugin built with
`qgis-sdk build` carries a private copy and installs nothing.

> Experimental `0.x`. Each `0.Y.0` carries migration notes; nothing is
> promised stable before `1.0.0`.

## Installation

```sh
pip install qgis-sdk-runtime          # the QGIS Python console, or a host script
pip install qgis-sdk                  # the developer kit: runtime + tools
```

## Example

```python
from qgis_sdk import action, describe_plugin, plugin


@plugin(title="Example tools")
class Tools:
    @action
    def run(self, request: int) -> int:
        return request


print(describe_plugin(Tools).to_json())
```

## Documentation

- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  declarations, runtime, adapters, the bridge host side, release and
  migration notes.
- [TypeScript bridge](https://www.npmjs.com/package/@archont561/qgis-sdk) -
  the companion package for a `QWebEngineView` interface.

## License

MIT
