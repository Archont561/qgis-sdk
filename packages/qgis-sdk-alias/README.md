# qgis-sdk (npm)

**Unscoped alias of [`@archont561/qgis-sdk`](https://www.npmjs.com/package/@archont561/qgis-sdk).**

There is no code of its own. Every entry point of the scoped package has its
counterpart here, and the manifest pins the dependency to the exact same
version, so `qgis-sdk@X` installs `@archont561/qgis-sdk@X` under the shorter name. Pick
whichever reads better in your project; both names publish from one tag.

> Status: experimental `0.x`; released with every `@archont561/qgis-sdk` release, at
> the same version, under the same license.

## Installation

```sh
bun add qgis-sdk
npm install qgis-sdk
```

## Example

```ts
import { QgisSdk } from "qgis-sdk";
import { useOperation } from "qgis-sdk/react";
import { createBridgeHarness } from "qgis-sdk/testing";
import schema from "./bridge.schema";

const qgis = QgisSdk.fromBridgeSchema(schema);
```

Entry points: `qgis-sdk`, `qgis-sdk/bridge`, `qgis-sdk/host`, `qgis-sdk/react`,
`qgis-sdk/vue`, `qgis-sdk/svelte`, `qgis-sdk/testing`.

## Documentation

- [TypeScript package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md) -
  the scoped package's guide; everything in it applies under this name.
- [`@archont561/qgis-sdk`](https://github.com/Archont561/qgis-sdk/tree/main/packages/qgis-sdk-typescript) -
  the package this one re-exports, and its own README.

## License

MIT
