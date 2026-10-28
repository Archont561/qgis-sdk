# @archont561/qgis-sdk

**Bring typed QGIS plugin actions to your web UI.**

Build a `QgisSdk` client from your Python plugin's generated schema, call
its actions and streams, and use granted host services. Framework-free stores
and React, Vue and Svelte bindings help build interfaces in `QWebEngineView`;
a scripted host lets you test them without QGIS.

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
