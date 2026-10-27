# qgis-sdk-ui (npm)

**Unscoped alias of [`@archont561/qgis-sdk-ui`](https://www.npmjs.com/package/@archont561/qgis-sdk-ui).**

There is no code of its own. Every entry point of the scoped package has its
counterpart here, and the manifest pins the dependency to the exact same
version, so `qgis-sdk-ui@X` installs `@archont561/qgis-sdk-ui@X` under the shorter name. Pick
whichever reads better in your project; both names publish from one tag.

> Status: experimental `0.x`; released with every `@archont561/qgis-sdk-ui` release, at
> the same version, under the same license.

## Installation

```sh
bun add qgis-sdk-ui
npm install qgis-sdk-ui
```

## Example

```ts
import "qgis-sdk-ui/define"; // registers every <qgis-*> element
import "qgis-sdk-ui/style.css";
import { QgisLayerPicker } from "qgis-sdk-ui/react";
```

Entry points: `qgis-sdk-ui`, `qgis-sdk-ui/define`, `qgis-sdk-ui/react`,
`qgis-sdk-ui/vue`, `qgis-sdk-ui/svelte`, `qgis-sdk-ui/uno`; the stylesheets
`qgis-sdk-ui/style.css` and `qgis-sdk-ui/tokens.css` `@import` the scoped ones.

## Documentation

- [TypeScript package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md) -
  the scoped package's guide; everything in it applies under this name.
- [`@archont561/qgis-sdk-ui`](https://github.com/Archont561/qgis-sdk/tree/main/packages/qgis-sdk-ui) -
  the package this one re-exports, and its own README.

## License

MIT
