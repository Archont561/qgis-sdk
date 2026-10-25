# qgis-sdk (npm)

**Unscoped alias of [`@archont561/qgis-sdk`](https://www.npmjs.com/package/@archont561/qgis-sdk).**

Every entry point re-exports the scoped package at the exact same version:
`qgis-sdk`, `qgis-sdk/bridge`, `qgis-sdk/host`, `qgis-sdk/react` and
`qgis-sdk/testing`. There is no code of its own; pick whichever name reads
better in your project. The Python package of the same name is on
[PyPI](https://pypi.org/project/qgis-sdk/).

## Installation

```sh
bun add qgis-sdk
npm install qgis-sdk
```

## Example

```ts
import { BridgeClient } from "qgis-sdk/bridge";
import { createHost } from "qgis-sdk/host";
```

## Documentation

- [TypeScript package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md) -
  exports, the transport client, host namespaces, generated clients, streams,
  the React bindings and testing against a scripted host.

## License

MIT
