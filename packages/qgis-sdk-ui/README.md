# @archont561/qgis-sdk-ui

**Light-DOM web components for QGIS plugin pages, on the
[`@archont561/qgis-sdk`](https://www.npmjs.com/package/@archont561/qgis-sdk)
store core - the web half of the SDK's UI catalogue.**

A form over a declared action, layer, field and CRS pickers, file and
directory inputs, a distance, a choice, a progress bar, a log and a run
button, each named and keyworded as its native counterpart. Every element
is a Lit element rendering into itself, so the page's stylesheet reaches
each control and a `<label for>` works; each carries `data-qgis-sdk` and
`data-part="label|control|error"` hooks. Styling is a compiled `style.css`
of `qs-` utilities bound to `--qgis-sdk-*` tokens the host palette fills.
`./react`, `./vue` and `./svelte` wrap the same elements.

> Status: `0.1.0`, experimental; the first npm release follows the
> `ui-v*` tag under this name and the unscoped alias `qgis-sdk-ui`. `lit`
> is the only dependency, `@archont561/qgis-sdk` a peer; `./react` needs
> `react` and `@lit/react`, `./vue` needs `vue`, `./svelte` needs
> `svelte`, `./uno` needs `@unocss/preset-mini`.

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
<qgis-layer-picker name="layer_id" label="Layer" required></qgis-layer-picker>
<qgis-job-progress label="Job"></qgis-job-progress>
```

```tsx
import { QgisLayerPicker } from "@archont561/qgis-sdk-ui/react";
<QgisLayerPicker qgis={qgis} name="layer_id" label="Layer" required onQgisChange={pick} />;
```

A page outside QGIS, or one without the `layers.read` grant, sees the
pickers say so instead of a fault; `applyHostTheme(qgis)` takes the running
QGIS palette once the handshake answered.

## Documentation

- [TypeScript package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md) -
  the elements, their properties in both spellings, the wrappers, the
  `--qgis-sdk-*` variables and the `./uno` preset.
- Storybook: `bun run storybook` in `packages/qgis-sdk-ui` serves every
  component with a theme switcher and the a11y addon; the static build
  joins the docs site when it ships.

## License

MIT
