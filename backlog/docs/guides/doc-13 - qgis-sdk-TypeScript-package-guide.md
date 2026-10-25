---
id: doc-13
title: qgis-sdk TypeScript package guide
type: guide
created_date: '2026-10-24 21:20'
---
# qgis-sdk TypeScript package guide

The reference prose for `@archont561/qgis-sdk`. It used to live in
`packages/qgis-sdk-typescript/README.md`; [decision-29](../../decisions/decision-29%20-%20Keep-READMEs-minimal-and-hold-reference-prose-in-backlog-guides-until-the-docs-site.md)
moved it here as the source for the documentation site
([TASK-43](../../tasks/task-43%20-%20Publish-a-Starlight-documentation-site-from-the-backlog-guides.md)).
Status at the time of writing: `0.2.0` released with the Python `0.3.0`
milestone ([decision-25](../../decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md));
it carries the transport client, the host namespaces and the generated clients
described below. Through `0.2.0` the package was published as
`@archont561/qgis-sdk-bridge`; it is `@archont561/qgis-sdk` from `0.3.0` on
([decision-33](../../decisions/decision-33%20-%20Rename-the-npm-package-to-archont561-qgis-sdk-and-suffix-the-package-directories.md)).
Migration notes are at the end of this guide.

The Python half of every surface here is in [doc-12](doc-12%20-%20qgis-sdk-Python-package-guide.md).

## Installation

Install from [npm](https://www.npmjs.com/package/@archont561/qgis-sdk) or [GitHub Packages](https://github.com/Archont561/qgis-sdk/pkgs/npm/qgis-sdk):

```sh
bun add @archont561/qgis-sdk
# or with npm:
npm install @archont561/qgis-sdk
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
} from "@archont561/qgis-sdk";
```

- **Safe integer bounds:** `MAX_SAFE_INTEGER` (`9007199254740991`), `MIN_SAFE_INTEGER` (`-9007199254740991`), and `isSafeJsonInteger(value)` mirror `qgis_sdk.models.MAX_SAFE_INTEGER` and `SafeJsonInteger`.
- **Version 1 plugin descriptions:** `parsePluginDescription(raw)` validates and freezes `PluginDescription` payloads (`schema_version: 1`) produced by Python's `describe_plugin(cls).to_json()`.
- **Structured SDK errors:** Every SDK exception class begins with `QgisSdk` and carries a stable wire `code` property (`"sdk_error"`, `"scope_closed"`, `"unsupported_capability"`, `"invalid_declaration"`, `"contract_validation_failed"`).

## Transport client

The `./bridge` subpath is the client half of the Python host's dispatcher. It
speaks envelopes over an injected transport, so a test can script a failure
instead of reproducing one inside a running QGIS.

```ts
import { BridgeClient } from "@archont561/qgis-sdk/bridge";

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

## Host namespaces

`./host` is the curated host surface a page may call (decision-27). It is
generated from `qgis_sdk.bridge.host`, ships inside this package, and is versioned
with it, so it cannot drift from the Python it talks to.

```ts
import { createHost } from "@archont561/qgis-sdk/host";

const host = createHost(client);
const page = await host.layers.list({ limit: 20 });
const layer = await host.layers.get({ layer_id: page.items[0]!.id });
const theme = await host.settings.get({ key: "theme", default: "light" });
```

- **The declared inventory:** `layers.list`, `layers.get`, `project.layer_ids`,
  `settings.get`, `notifications.info`, `styles.apply`. Anything else of the QGIS
  API is not reachable from a page; the operations it would need wait for their
  owning task, and the Python manifest records which.
- **Paged, never unbounded.** Every list takes `{limit?, cursor?}` and returns
  `{items, truncated, next_cursor?}`. `limit` is capped at 200, and the generated
  validator refuses a larger one before the call leaves the page. A cursor is
  only ever the value the host handed back in `next_cursor`: anything else is
  refused as `invalid_payload` instead of being read as "start over", and the
  generated validator refuses it before the call leaves the page.
- **Typed results.** `host.layers.get` returns `VectorLayerInfo`, not a record:
  `geometry_type` is one of the declared literals and `crs` is `string | null`.
- **The same asymmetry as plugin operations.** Arguments are closed (an unknown
  one is a `HostContractError` before the transport), responses are additive (a
  field a newer host added is tolerated, a missing one is refused).
- **Versioned.** `HOST_SCHEMA_VERSION` and `HOST_OPERATIONS` are exported, and the
  handshake advertises the same version, so a page can tell what it is talking to
  before its first call.

## Generated clients

`client.invoke<T>(...)` is a transport, not a type guarantee: `T` is asserted by
hand at the call site. For operations, generate the client from the plugin's own
declarations instead:

```console
$ qgis-sdk bridge generate --plugin my_plugin.bridge:MyPlugin --out web/src/bridge.ts
```

The module imports nothing from this package. It exports the declared value types,
`OPERATIONS` and `OperationId`, one validator per type, and a nested operation map:

```ts
import { createOperations, type PluginOperations } from "./bridge";

const operations: PluginOperations = createOperations(client);
const summary = await operations.sites.summary({ layer_id: "sites" });
```

- **Compile time.** An operation the plugin did not declare is not a member of the
  map, and a misspelled or mistyped argument is a type error - including an
  unknown property inside a nested object.
- **Runtime.** The same generated module validates what it sends (strict: unknown
  arguments are refused before the transport is touched) and what comes back
  (lenient: a field a newer host added is tolerated, a missing one is a
  `ContractError` naming the operation).
- **Owned by CI.** The file is generated source, never edited by hand: the plugin's
  CI regenerates it and fails when the checked-in copy differs. `CONTRACT_FINGERPRINT`
  identifies the wire contract the file was built from.
- **Streams are operations too (decision-28).** A method the plugin marked with
  `@stream(id="sites.watch", events={"data": SiteChange, "progress": ScanProgress})`
  becomes a member that takes the request, the handlers and returns the same
  `StreamHandle` as `client.subscribe`. The module generates one type per
  declared event kind and a discriminated `SitesWatchEvent` union, so
  `onEvent` narrows on `event.kind`; a frame whose payload does not match the
  declared schema ends the subscription with an `error` terminal instead of
  reaching the handler. The frame envelope - `seq`, `gap`, `close()` - stays in
  this package's kernel, and a module with no declared stream renders no
  stream support at all.

```ts
const handle = await operations.sites.watch(
	{ layer_id: "sites" },
	{
		onEvent: (event) => {
			if (event.kind === "data") render(event.payload.change);
		},
		onTerminal: (terminal) => console.info("stream ended:", terminal.kind),
	},
);
```

## React bindings

`./react` is an optional entry point ([decision-18](../../decisions/decision-18%20-%20Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md)):
it is the only subpath that imports React, `react` is an optional peer, and
the root, `./bridge` and `./host` stay free of any framework or browser global
(`tests/surface.test.ts` bundles them and fails on a stray `react`). The
bindings add no second client. A `BridgeProvider` shares the same `BridgeClient`
a vanilla page builds, and the hooks take the members a generated module already
exports, so the typed contract is the generated one.

```ts
import { BridgeProvider, useOperation, useOperations, useStream } from "@archont561/qgis-sdk/react";
import { createOperations } from "./bridge";

function App() {
	// Owns a client for `transport` and closes it on unmount. Pass `client`
	// instead to share one the page already owns; the provider then never
	// closes it. Exactly one of the two is required.
	return createElement(BridgeProvider, { transport }, createElement(Sites));
}

function Sites() {
	const operations = useOperations(createOperations); // memoised per client
	const [summary, loadSummary] = useOperation(operations.sites.summary);
	const watch = useStream(operations.sites.watch, { layer_id: "sites" }, {
		onEvent: (event) => { if (event.kind === "data") render(event.payload.change); },
	});
	// summary.status: idle | pending | ok (value) | error (error)
	// watch.status:   idle | opening | open | ended (terminal) | failed (error)
}
```

- **`useOperation(fn)`** returns `[state, run, { abort, reset }]`. `run(input)`
  resolves with the value, or with `undefined` when the call failed, was aborted
  or was superseded - the state carries the error, so the promise never rejects
  into an event handler. Only the latest run can change the state; unmounting
  aborts whatever is in flight and settles nothing afterwards.
- **`useStream(open, input | null, handlers)`** keeps one subscription open
  while the component is mounted. It follows the *content* of `input` (a new
  object with equal fields does not reopen it), `null` closes it, handlers are
  read fresh on every frame, and unmount closes the stream even when the host
  has not acknowledged it yet. A host terminal moves the state to `ended`; a
  refused subscription is `failed` with the `QgisSdkBridgeRemoteError`.
- **StrictMode.** The simulated remount closes the owned client and the hook
  subscriptions; the effects that follow make exactly one new client and one
  new subscription, which the tests assert through the harness below.
- **Unmounting the provider** closes an owned client, which detaches the
  transport; a closed client sends no unsubscribe, the view going away is what
  disposes its subscriptions host-side ([decision-23](../../decisions/decision-23%20-%20Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md)).
  Unmounting a component under a live provider does send one.

## Testing against a scripted host

`./testing` is a `WireTransport` a test hands to its own `BridgeClient`, so the
page's real client, the generated module's validation and the React bindings
all run unchanged against a host the test scripts. Nothing global is mutated:
two harnesses are two hosts, and a test can prove nothing crosses between
their clients.

```ts
import { BridgeClient } from "@archont561/qgis-sdk/bridge";
import { SILENCE, createBridgeHarness, fault } from "@archont561/qgis-sdk/testing";
import { type OperationId, createOperations } from "./bridge";

const harness = createBridgeHarness<OperationId>();
const operations = createOperations(new BridgeClient(harness));

harness.expectInvoke<SitesSummaryRequest, SitesSummaryResult>("sites.summary", (payload) => ({ total: 1, largest: payload.layer_id, mode: "fast" }));
harness.expectInvoke("sites.summary", () => fault("forbidden", "not yours"));
harness.expectInvoke("sites.summary", () => SILENCE); // the client's own timeout speaks
harness.expectSubscribe("sites.watch", (_payload, stream) => {
	stream.emit("data", { change: "added" });
	stream.skip(2); // the next frame is a gap, ended the way the kernel promises
	stream.end({ kind: "complete" });
});

await operations.sites.summary({ layer_id: "sites" });
harness.calls;      // every envelope the client sent, in order
harness.assertSatisfied(); // unmet expectations, unexpected calls, open subscriptions, handler throws
```

- Expectations are consumed FIFO per operation. A call no expectation covers is
  answered with the `unexpected_call` failure code and remembered; a handler
  that throws answers `harness_error` and is reported by `assertSatisfied()`.
  Both are `QgisSdkBridgeHarnessError`s, as is an envelope that is not
  protocol 1.
- Deliveries are asynchronous and ordered: an acknowledgement reaches the
  client before the first frame a script emitted, and `await harness.settled()`
  waits for everything queued.
- `expectSubscribe(op, script, { ack })` delays the acknowledgement until the
  `ack()` promise settles, for tests of what a component does while a
  subscription is still opening.
- **Evidence boundary.** A green harness test says the page handles the frames
  a host *could* send; it says nothing about a `QWebEngineView` or a running
  host. That evidence lives in the Python suite and the qualification harnesses
  of [doc-14](doc-14%20-%20Workspace-development-qualification-harnesses-and-evidence.md). Keep
  the two apart in reports and never cite a mocked run as native behaviour.

## 0.2.0 migration notes

`0.2.0` is the first bridge release since `0.1.1` and the first cut under its
own tag (`ts-v0.2.0`); the Python SDK it pairs with is `0.3.0`.

- **No breaking change in the root entry.** Every export of `0.1.1` is still
  exported from `@archont561/qgis-sdk` with the same shape;
  `parsePluginDescription` additionally reads the `streams` list a Python
  `0.3.0` description carries. New root exports: `StreamDescription`,
  `StreamEventKind`, `isPlainRecord`.
- **`PLUGIN_DESCRIPTION_SCHEMA_VERSION` stays `1`**, matching the Python
  declarations; `scripts/release.py verify-versions` refuses a pair that
  disagrees. The transport speaks `protocol: 1`.
- **New entry points**, each an optional import: `./bridge` (the transport
  client, frames and refusal codes), `./host` (the generated host namespaces),
  `./react` (thin hooks; `react >= 18` is an optional peer dependency and is
  required only by this entry) and `./testing` (the scripted host harness).
  Consumers of `0.1.1` import nothing from them unless they choose to.
- **Manifest:** `package.json` carries `0.2.0`. Verify with
  `python scripts/release.py verify-versions --scope typescript --version 0.2.0`.

## Unreleased migration notes

- **Package renamed.** `@archont561/qgis-sdk-bridge` is now
  `@archont561/qgis-sdk`, published first as `0.3.0` with the exports of
  `0.2.0` unchanged ([decision-33](../../decisions/decision-33%20-%20Rename-the-npm-package-to-archont561-qgis-sdk-and-suffix-the-package-directories.md)).
  Replace the dependency and the import specifiers; the subpaths keep their
  names (`@archont561/qgis-sdk/bridge`, `/host`, `/react`, `/testing`). The
  old name stays installable and is deprecated on npm with a pointer here.
- **Repository layout.** The source moved from `packages/qgis-sdk-bridge` to
  `packages/qgis-sdk-typescript`; the Python package moved from
  `packages/qgis-sdk` to `packages/qgis-sdk-python`. Only contributors and
  the generated-file paths in CI are affected.
