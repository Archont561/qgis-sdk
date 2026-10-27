# qgis-sdk-ui (npm)

**Unscoped alias of [`@archont561/qgis-sdk-ui`](https://www.npmjs.com/package/@archont561/qgis-sdk-ui).**

Every entry point re-exports the scoped package at the exact same version:
`qgis-sdk-ui`, `qgis-sdk-ui/define`, `qgis-sdk-ui/react`, `qgis-sdk-ui/vue`,
`qgis-sdk-ui/svelte` and `qgis-sdk-ui/uno`; `qgis-sdk-ui/style.css` and
`qgis-sdk-ui/tokens.css` `@import` the scoped stylesheets. There is no code
of its own; pick whichever name reads better in your project.

## Installation

```sh
bun add qgis-sdk-ui
npm install qgis-sdk-ui
```

## Example

```ts
import "qgis-sdk-ui/define"; // registers every <qgis-*> element
import "qgis-sdk-ui/style.css";
```

## Documentation

- [TypeScript package guide, components section](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#components-archont561qgis-sdk-ui) -
  the elements, their properties in both spellings, the wrappers, the
  stylesheets and the UnoCSS preset.

## License

MIT
