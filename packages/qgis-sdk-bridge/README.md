# @archont561/qgis-sdk-bridge

**TypeScript client for QGIS plugin interfaces hosted in `QWebEngineView`.**

The companion to [`qgis-sdk`](https://pypi.org/project/qgis-sdk/): a correlated
transport client with subscriptions, the curated host namespaces, and the
contract a generated per-plugin client is built on. Every exported error begins
with `QgisSdk` and carries a stable wire `code`.

> Experimental. `0.1.1` on npm carries the description parser, the safe-integer
> wire bounds and the error hierarchy; `0.2.0`, which ships with the Python
> `0.3.0` milestone, adds `./bridge`, `./host`, the generated clients shown
> below, the optional `./react` bindings and the `./testing` harness.

## Installation

```sh
bun add @archont561/qgis-sdk-bridge
npm install @archont561/qgis-sdk-bridge
```

## Example

```ts
import { BridgeClient } from "@archont561/qgis-sdk-bridge/bridge";
import { createHost } from "@archont561/qgis-sdk-bridge/host";

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

- [TypeScript bridge guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-13%20-%20qgis-sdk-bridge-TypeScript-package-guide.md) -
  exports, the transport client, host namespaces, generated clients, streams,
  the React bindings and testing against a scripted host.
- [Python package guide](https://github.com/Archont561/qgis-sdk/blob/main/backlog/docs/guides/doc-12%20-%20qgis-sdk-Python-package-guide.md) -
  the host half of every surface above.

## License

MIT
