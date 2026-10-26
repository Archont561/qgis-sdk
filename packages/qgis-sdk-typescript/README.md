# @archont561/qgis-sdk

**TypeScript client for QGIS plugin interfaces hosted in `QWebEngineView`.**

The companion to [`qgis-sdk`](https://pypi.org/project/qgis-sdk/): a correlated
transport client with subscriptions, the curated host namespaces, and the
contract a generated per-plugin client is built on. Every exported error begins
with `QgisSdk` and carries a stable wire `code`.

> Experimental. Published as `@archont561/qgis-sdk-bridge` through `0.2.0`;
> `@archont561/qgis-sdk` continues from `0.3.0`. The root exports the
> transport client, the error root, the description contract and the
> framework-free stores; `./host`, `./react`, `./vue`, `./svelte` and
> `./testing` are opt-in entry points.

## Installation

```sh
bun add @archont561/qgis-sdk
npm install @archont561/qgis-sdk
```

## Example

```ts
import { BridgeClient } from "@archont561/qgis-sdk";
import { createHost } from "@archont561/qgis-sdk/host";

const client = new BridgeClient({
	send: (message) => channel.send(JSON.stringify(message)),
	subscribe: (listener) => {
		channel.onmessage = (text: string) => listener(JSON.parse(text));
		return () => {
			channel.onmessage = null;
		};
	},
});

const host = createHost(client);
const page = await host.layers.list({ limit: 20 });
```

A plugin's own operations come from the client `qgis-sdk bridge generate`
renders from its Python declarations.

## Documentation

- [TypeScript package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-TypeScript-package-guide.md) -
  exports, the transport client, host namespaces, generated clients, streams,
  the stores, the React, Vue and Svelte bindings and testing against a
  scripted host.
- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  the host half of every surface above.

## License

MIT
