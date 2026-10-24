# @archont561/qgis-sdk-bridge

**TypeScript contract, wire-limit, and error primitives for QGIS `QWebEngineView` plugin interfaces.**

`@archont561/qgis-sdk-bridge` is the TypeScript companion package to [`qgis-sdk`](https://pypi.org/project/qgis-sdk/) in the [QGIS SDK workspace](https://github.com/Archont561/qgis-sdk).

> **Status (`0.1.0` experimental):** Exposes the version 1 plugin/action declaration parser (`parsePluginDescription`, `PluginDescription`, `ActionDescription`), JavaScript-safe integer wire bounds (`MAX_SAFE_INTEGER`, `MIN_SAFE_INTEGER`, `isSafeJsonInteger`), and the `QgisSdk*`-prefixed error hierarchy (`QgisSdkError`, `QgisSdkScopeClosedError`, `QgisSdkUnsupportedCapabilityError`, `QgisSdkDeclarationError`, `QgisSdkContractValidationError`, `QgisSdkValidationIssue`). `QWebChannel` transport bindings, generated operation clients, and React hooks are scheduled for subsequent `0.x` milestones.

## Installation

Install from [npm](https://www.npmjs.com/package/@archont561/qgis-sdk-bridge) or [GitHub Packages](https://github.com/Archont561/qgis-sdk/pkgs/npm/qgis-sdk-bridge):

```sh
bun add @archont561/qgis-sdk-bridge
# or with npm:
npm install @archont561/qgis-sdk-bridge
```

## Exports

```ts
import {
	MAX_SAFE_INTEGER,
	MIN_SAFE_INTEGER,
	PLUGIN_DESCRIPTION_SCHEMA_VERSION,
	QgisSdkContractValidationError,
	QgisSdkDeclarationError,
	QgisSdkError,
	QgisSdkScopeClosedError,
	QgisSdkUnsupportedCapabilityError,
	QgisSdkValidationIssue,
	isSafeJsonInteger,
	parsePluginDescription,
} from "@archont561/qgis-sdk-bridge";
```

- **Safe integer bounds:** `MAX_SAFE_INTEGER` (`9007199254740991`), `MIN_SAFE_INTEGER` (`-9007199254740991`), and `isSafeJsonInteger(value)` mirror `qgis_sdk.models.MAX_SAFE_INTEGER` and `SafeJsonInteger`.
- **Version 1 plugin descriptions:** `parsePluginDescription(raw)` validates and freezes `PluginDescription` payloads (`schema_version: 1`) produced by Python's `describe_plugin(cls).to_json()`.
- **Structured SDK errors:** Every SDK exception class begins with `QgisSdk` and carries a stable wire `code` property (`"sdk_error"`, `"scope_closed"`, `"unsupported_capability"`, `"invalid_declaration"`, `"contract_validation_failed"`).

## Transport client

The `./bridge` subpath is the client half of the Python host's dispatcher. It
speaks envelopes over an injected transport, so a test can script a failure
instead of reproducing one inside a running QGIS.

```ts
import { BridgeClient } from "@archont561/qgis-sdk-bridge/bridge";

const client = new BridgeClient({
	send: (message) => channel.send(JSON.stringify(message)),
	subscribe: (listener) => {
		const handler = (text: string): void => listener(JSON.parse(text));
		channel.onmessage = handler;
		return () => {
			channel.onmessage = null;
		};
	},
});

const layer = await client.invoke("layers.info", { layer_id: "sites" });
```

- **Correlated calls:** a reply that names no pending call is counted, never
  delivered to whichever call happens to be waiting.
- **Three different outcomes:** a local abort, a timeout and a closed client are
  three errors, and a timeout says the outcome is unknown. Nothing is retried
  automatically.
- **Subscriptions:** `client.subscribe(operation, payload, { onEvent, onTerminal })`
  resolves with a handle once the host acknowledges it. Frames must arrive with
  a `seq` that continues the sequence; anything else ends the subscription with a
  `gap` terminal instead of delivering out of order. `close()` notifies the host
  once, and closing an already-ended subscription sends nothing.

```ts
const subscription = await client.subscribe("project.changes", {}, {
	onEvent: (event) => render(event.payload),
	onTerminal: (terminal) => console.info("stream ended:", terminal.kind),
});

subscription.close();
```

Protocol version 1 is unchanged by subscriptions: a client that never subscribes
still sees nothing but the replies to its own calls.

## License

MIT
