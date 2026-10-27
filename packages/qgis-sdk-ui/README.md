# @archont561/qgis-sdk-ui

**Light-DOM web components for QGIS plugin pages, on the
[`@archont561/qgis-sdk`](https://www.npmjs.com/package/@archont561/qgis-sdk)
store core.**

The web half of the SDK's UI catalogue: a form over a declared action, layer,
field and CRS pickers, file and directory inputs, a distance, a choice, a
progress bar, a log and a run button. Each is a Lit element rendering into
itself, so the page's stylesheet reaches every control and a `<label for>`
works; each carries `data-qgis-sdk` and `data-part="label|control|error"`
hooks. Styling is a compiled `style.css` of `qs-` utilities bound to
`--qgis-sdk-*` tokens, which the host palette fills inside QGIS.

> Experimental. `lit` is the only dependency; `@archont561/qgis-sdk` is a
> peer. `./uno` needs `@unocss/preset-mini`.

## Installation

```sh
bun add @archont561/qgis-sdk-ui
npm install @archont561/qgis-sdk-ui
```

## Example

```ts
import "@archont561/qgis-sdk-ui/define"; // registers every <qgis-*> element
import "@archont561/qgis-sdk-ui/style.css";
import { formStore, QgisSdk } from "@archont561/qgis-sdk";
import schema from "./bridge.schema";

const qgis = QgisSdk.fromBridgeSchema(schema);
const form = document.querySelector("qgis-form");
form.qgis = qgis;
form.store = formStore(qgis, "buffer");
```

```html
<qgis-form label="Buffer"></qgis-form>
<qgis-layer-picker name="layer_id" label="Layer"></qgis-layer-picker>
<qgis-job-progress label="Job"></qgis-job-progress>
```

A page outside QGIS, or one without the `layers.read` grant, sees the pickers
say so instead of a fault.

## Documentation

- [TypeScript package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md) -
  the components, the wrappers, the `--qgis-sdk-*` variables and the
  `./uno` preset.

## License

MIT
