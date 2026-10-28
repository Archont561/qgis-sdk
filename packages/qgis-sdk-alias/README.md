# @archont561/qgis-sdk

**The TypeScript SDK for QGIS plugin interfaces hosted in `QWebEngineView`:
one typed object over the plugin's own declarations.**

The page side of [`qgis-sdk`](https://pypi.org/project/qgis-sdk/). A page
builds `QgisSdk` from the schema `qgis-sdk bridge generate` renders from the
plugin's Python declarations and gets one typed method per action and
stream, the curated host namespaces (`layers`, `project`, `files`,
`algorithms`, ...), framework-free stores and React, Vue and Svelte
bindings over them, and a scripted harness for tests. Every exported error
begins with `QgisSdk` and carries a stable wire `code`.

> Status: `0.5.0`, experimental `0.x`. Published as
> `@archont561/qgis-sdk-bridge` through `0.2.0`; this name continues from
> `0.3.0`, and `qgis-sdk` on npm is its unscoped alias. `./host`, `./react`,
> `./vue`, `./svelte` and `./testing` are opt-in entry points.

## Installation

```sh
bun add @archont561/qgis-sdk        # or its unscoped alias: bun add qgis-sdk
npm install @archont561/qgis-sdk    # or: npm install qgis-sdk
```

`qgis-sdk` on npm re-exports every entry point of `@archont561/qgis-sdk`
at the same version; the two names share this README.

## Example

```ts
import { QgisSdk, formStore } from "@archont561/qgis-sdk";
import schema from "./bridge.schema"; // qgis-sdk bridge generate

const qgis = QgisSdk.fromBridgeSchema(schema);
const buffered = await qgis.buffer({ layer_id, distance: 25 }); // typed by the schema
const layers = await qgis.host.layers.list({ limit: 20 });        // a granted host namespace

const form = formStore(qgis, "buffer"); // fields from the action's schema; drives <qgis-form>
```

The same stores back `useForm`/`useOperation` in `./react`, the Vue
composables and the Svelte stores; `./testing` scripts a host without QGIS.

## Documentation

- [TypeScript package guide](https://archont561.github.io/qgis-sdk/typescript/) -
  exports, `QgisSdk`, the transport client, host namespaces, streams, the
  stores, the React, Vue and Svelte bindings, Processing from a page and
  testing against a scripted host.
- [`@archont561/qgis-sdk-ui`](https://github.com/Archont561/qgis-sdk/tree/main/packages/qgis-sdk-ui) -
  the web components on these stores.
- [Python package guide](https://archont561.github.io/qgis-sdk/python/) -
  the host half of every surface above.

## License

MIT
