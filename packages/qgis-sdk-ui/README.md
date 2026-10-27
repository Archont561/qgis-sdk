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

> Experimental, `0.1.0` unpublished: the first npm release follows the
> `ui-v*` tag. `lit` is the only dependency; `@archont561/qgis-sdk` is a
> peer. `./react` needs `react` and `@lit/react`, `./vue` needs `vue`,
> `./svelte` needs `svelte`, `./uno` needs `@unocss/preset-mini`.

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
say so instead of a fault. `applyHostTheme(qgis)` takes the running QGIS
palette once the handshake answered and leaves the documented defaults
otherwise.

### Frameworks

```tsx
import { QgisLayerPicker } from "@archont561/qgis-sdk-ui/react";
<QgisLayerPicker qgis={qgis} name="layer_id" label="Layer" onChange={pick} />;
```

```vue
<QgisLayerPicker :qgis="qgis" name="layer_id" label="Layer" @change="pick" />
```

```svelte
<qgis-layer-picker {qgis} name="layer_id" label="Layer" onqgis-change={pick} />
```

The React components come from `@lit/react`; the Vue ones bind every property
as a property and re-emit `change`, `result`, `run` and `cancel`; Svelte sets
properties on a registered element by itself, and `use:qgisProps` does it for
a `<svelte:element>`.

## Documentation

- [TypeScript package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md) -
  the components, the wrappers, the `--qgis-sdk-*` variables and the
  `./uno` preset.
- Storybook: `bun run storybook` in `packages/qgis-sdk-ui` serves every
  component with a light/dark theme switcher and the a11y addon; the static
  build joins the docs site when it exists.

## License

MIT
