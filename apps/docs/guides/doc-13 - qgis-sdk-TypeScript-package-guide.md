---
id: doc-13
title: qgis-sdk TypeScript package guide
type: guide
created_date: '2026-10-24 21:20'
---
# qgis-sdk TypeScript package guide

The reference for `@archont561/qgis-sdk`, the page side of a plugin's web
view: the transport client, the host namespaces, the generated schema module
and `QgisSdk`, the framework-free stores with their React, Vue and Svelte
bindings, the `@archont561/qgis-sdk-ui` components and the scripted test host.
The documentation site at
[archont561.github.io/qgis-sdk](https://archont561.github.io/qgis-sdk/)
renders it one page per section. Status at the time of writing: `0.5.0` is the released version (`ts-v0.5.0`,
tagged with `python-v0.7.0` and `ui-v0.1.0` on one merge commit as the 0.7.0
triple; packages version independently,
[decision-25](../../../backlog/decisions/decision-25%20-%20Version-each-package-independently-behind-a-shared-contract-version.md));
it carries the framework-free stores with the `./vue` and `./svelte`
adapters and `algorithms.run`, described below and in the 0.5.0 migration
notes; `0.4.0` brought the root entry and the `QgisSdk` entry point. `0.3.0` was the first version under
this name. Through `0.2.0` the package was published as
`@archont561/qgis-sdk-bridge`; it is `@archont561/qgis-sdk` from `0.3.0` on
([decision-33](../../../backlog/decisions/decision-33%20-%20Rename-the-npm-package-to-archont561-qgis-sdk-and-suffix-the-package-directories.md)).
Migration notes are at the end of this guide.

The Python half of every surface here is in [doc-12](doc-12%20-%20qgis-sdk-Python-package-guide.md).

## Installation

Install from [npm](https://www.npmjs.com/package/@archont561/qgis-sdk) or [GitHub Packages](https://github.com/Archont561/qgis-sdk/pkgs/npm/qgis-sdk):

```sh
bun add @archont561/qgis-sdk
# or with npm:
npm install @archont561/qgis-sdk
```

The unscoped name `qgis-sdk` is an alias published from the same tag: it
depends on `@archont561/qgis-sdk` at the exact same version and re-exports
every entry (`qgis-sdk`, `qgis-sdk/bridge`, `qgis-sdk/host`, `qgis-sdk/react`,
`qgis-sdk/vue`, `qgis-sdk/svelte`, `qgis-sdk/testing`). Use whichever name
reads better; the surface is one.

## Exports

The root is the import a page needs: `QgisSdk`, the schema types, the
transport client, the error root, the version 1 plugin-description contract
and the [stores](#stores-the-framework-free-core). Everything under `./bridge`
is also exported from the root; the subpath stays for code that already uses
it.

```ts
import {
	BridgeClient,
	type BridgeSchema,
	MAX_SAFE_INTEGER,
	MIN_SAFE_INTEGER,
	PLUGIN_DESCRIPTION_SCHEMA_VERSION,
	QgisSdk,
	QgisSdkBridgeRemoteError,
	QgisSdkContractError,
	QgisSdkContractValidationError,
	QgisSdkDeclarationError,
	QgisSdkError,
	QgisSdkValidationIssue,
	QgisSdkWebChannelError,
	createWebChannelTransport,
	defineBridgeSchema,
	insideQgis,
	isSafeJsonInteger,
	parsePluginDescription,
	validateAgainstSchema,
} from "@archont561/qgis-sdk";
```

- **`QgisSdk`:** `QgisSdk.fromBridgeSchema(schema)` builds the page's typed
  handle on the plugin from its generated schema module, as documented under
  [The schema module and `QgisSdk`](#the-schema-module-and-qgissdk). The
  same name is the instance type: `QgisSdk<Operations, Streams>`.
- **Schema types:** `BridgeSchema<O, S>`, `OperationsOf<S>`, `StreamsOf<S>`
  and `defineBridgeSchema(...)`, the one import a generated schema module
  makes.
- **Default transport:** `insideQgis()` and
  `createWebChannelTransport(objectName)` are what `QgisSdk` uses when no
  `transport` is given; a page that builds its own `BridgeClient` can use them
  directly instead of hand-writing the `QWebChannel` glue.
- **Transport client:** `BridgeClient`, its options, frames, the parsers and
  the seven `QgisSdkBridge*Error` classes, as documented under
  [Transport client](#transport-client).
- **Safe integer bounds:** `MAX_SAFE_INTEGER` (`9007199254740991`), `MIN_SAFE_INTEGER` (`-9007199254740991`), and `isSafeJsonInteger(value)` mirror `qgis_sdk.models.MAX_SAFE_INTEGER` and `SafeJsonInteger`.
- **Version 1 plugin descriptions:** `parsePluginDescription(raw)` validates and freezes `PluginDescription` payloads (`schema_version: 1`) produced by Python's `describe(app).to_json()`. `qgis-sdk bridge generate` is the build-time reader of the same payload; a page only needs this one to render operations it did not generate a client for.
- **Structured SDK errors:** every error this package raises extends `QgisSdkError` and carries a stable wire `code` (`"sdk_error"`, `"invalid_declaration"`, `"contract_validation_failed"`, `"no_web_channel"`, the transport's refusal codes, and the code of a remote fault on `QgisSdkBridgeRemoteError`). Match on the code, not on the class name; a Python-side error such as `scope_closed` or `unsupported_capability` reaches a page as a `QgisSdkBridgeRemoteError` with that code, so the package carries no idle mirror class for it ([decision-40](../../../backlog/decisions/decision-40%20-%20Make-the-root-entry-the-page-import-and-keep-generated-plugin-clients-import-free.md)).

- **Stores:** `OperationStore`, `StreamStore`, `FormStore`/`formStore`,
  `HostQueryStore`/`layersQuery`/`layerFieldsQuery`, the `Store<T>` shape,
  their state types, `schemaFields`, `labelFor`, `stableKey` and
  `QgisSdkStoreError` (`"store_error"`), as documented under
  [Stores](#stores-the-framework-free-core).

What the root does **not** carry, and why: `./host` is generated and large, so
it is opt-in; `./react`, `./vue` and `./svelte` each need their optional peer;
`./testing` is a development dependency. The package exports no internal
helper.

### Which entry for which page

| Tier | Page | Entry points | Scaffold (`qgis-sdk new --web`) |
| --- | --- | --- | --- |
| 1 | Vanilla TypeScript | root (`QgisSdk` + stores) | `--web vanilla`: `formStore` + `layersQuery` page |
| 1 | React | root + `./react` | `--web react`: `useForm` + `useHostQuery` page |
| 2 | Vue 3 | root + `./vue` | none; wire it per [Vue bindings](#vue-bindings) |
| 2 | Svelte 5 | root + `./svelte` | none; wire it per [Svelte bindings](#svelte-bindings) |

Tier 1 is what the scaffold generates, the opt-in `QGIS_SDK_SCAFFOLD_WEB`
harness builds and QGIS loads in CI. Tier 2 ships the adapter with its own
test project and the wiring below, and is covered by the same behaviour suite
as the core and the React hooks (`tests/store-behaviour.ts`); it has no
scaffold template ([decision-47](../../../backlog/decisions/decision-47%20-%20Build-web-UI-on-a-framework-free-store-core-with-per-framework-adapters-and-ship-components-as-qgis-sdk-ui.md)).
Every adapter is one thin subscription layer over the stores: the behaviour
lives in the root, so a page can switch framework (or drop it) without
changing what the host sees.

## Transport client

The `./bridge` subpath is the client half of the Python host's dispatcher. It
speaks envelopes over an injected transport, so a test can script a failure
instead of reproducing one inside a running QGIS.

### Creating a client

```ts
import { BridgeClient } from "@archont561/qgis-sdk"; // or "@archont561/qgis-sdk/bridge"

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

### What the client guarantees

Calls and subscriptions have explicit outcomes and lifecycle guarantees.

### Correlated calls

A reply that names no pending call is counted, never delivered to whichever
call happens to be waiting.

### Three different outcomes

A local abort, a timeout and a closed client are three errors, and a timeout
says the outcome is unknown. Nothing is retried automatically.

### Subscriptions

`client.subscribe(operation, payload, { onEvent, onTerminal })` resolves with a
handle once the host acknowledges it. Frames must arrive with a `seq` that
continues the sequence; anything else ends the subscription with a `gap`
terminal instead of delivering out of order. `close()` notifies the host once,
and closing an already-ended subscription sends nothing.

```ts
const subscription = await client.subscribe("project.changes", {}, {
	onEvent: (event) => render(event.payload),
	onTerminal: (terminal) => console.info("stream ended:", terminal.kind),
});

subscription.close();
```

Protocol 2 adds the acknowledgement. Every frame the client delivers is answered
with a `{kind: "ack", subscription_id, seq}` message, sent after `onEvent`
returns and never for a terminal frame; without it the host holds a bounded
number of frames in flight (`MAX_IN_FLIGHT_FRAMES`, 8) and stops. Passing
`{acknowledge: false}` turns it off for a consumer that really does want the
raw pump, and then the queue is the host's to bound
([decision-59](../../../backlog/decisions/decision-59%20-%20Carry-large-and-binary-payloads-across-the-bridge-and-agent-boundaries-by-reference-with-bounded-pages-and-backpressure.md)).

A `seq` that does not continue the sequence ends the subscription with a `gap`
terminal, and recovery is a fresh `subscribe` with its own id, not a resume: the
host has already dropped the old subscription's position.

### Results too large to send: `BlobRef`

A reply above the inline ceiling does not arrive as a value. The host keeps the
bytes and answers with a `BlobRef` - `{kind: "blob", id, size, media_type,
checksum, expires_at}` - and the page fetches it in bounded chunks:

```ts
import { readBlob } from "@archont561/qgis-sdk/bridge";
import type { BlobRef } from "@archont561/qgis-sdk/host";

const value = (await client.invoke("algorithms.run", payload)) as
	| BlobRef
	| RunResult;
if (typeof value === "object" && value !== null && "kind" in value) {
	// `readBlob` follows `next_offset`, checks the size and verifies the sha256
	// before handing anything back.
	const bytes = await readBlob((input) => client.invoke("blob.get", input), value);
}
```

- **The ref is not a handle for another view.** A `blob` minted for one view is
  refused for another exactly like an unknown one, and disposal of the view
  releases the bytes.
- **Chunks are resumable.** Each `blob.get` answers `{offset, length, size,
  checksum, data_base64, next_offset}`; `next_offset` null ends the payload, so
  the loop is `offset = next_offset` until null. `MAX_BLOB_BYTES` (32 MiB) and
  `BLOB_TTL_SECONDS` (300) bound the payload and its life, and
  `MAX_BLOBS_PER_VIEW` (16) bounds how many a view can hold.
- **A result above the ceiling that is not a blob is a failure, not a
  truncation.** The host refuses with `invalid_result` naming the ceiling, and
  the client surfaces it as `QgisSdkBridgeRemoteError`.

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

- **The declared inventory:** `layers.list`, `layers.get`,
  `layers.open_vector`, `project.layer_ids`, `settings.get`,
  `notifications.info`, `styles.apply`, `files.export`, `blob.get`, the
  `network.fetch` stream, `algorithms.providers`, `algorithms.list`,
  `algorithms.describe`, `algorithms.run` (below) and, since 0.10.0,
  `features.page`, `features.get`, `expressions.evaluate`,
  `expressions.validate` and `editing.begin/add/update/delete/commit/rollback`.
  Anything else of the QGIS API is not reachable from a page; the operations it
  would need wait for their owning task, and the Python manifest records which.
- **Paged, never unbounded.** Every list takes `{limit?, cursor?}` and returns
  `{items, truncated, next_cursor?}`. `limit` is capped at 200 (1000 for a
  feature page, 100 by default), and the generated validator refuses a larger one
  before the call leaves the page. A cursor is only ever the value the host
  handed back in `next_cursor`: anything else is refused as `invalid_payload`
  instead of being read as "start over", and the generated validator refuses it
  before the call leaves the page.
- **Typed results.** `host.layers.get` returns `VectorLayerInfo`, not a record:
  `geometry_type` is one of the declared literals and `crs` is `string | null`.
- **The same asymmetry as plugin operations.** Arguments are closed (an unknown
  one is a `QgisSdkHostContractError` before the transport), responses are
  additive (a field a newer host added is tolerated, a missing one is refused).
  The error extends `QgisSdkError` with `code: "contract_validation_failed"`
  and names the `operation`.
- **Versioned.** `HOST_SCHEMA_VERSION` and `HOST_OPERATIONS` are exported, and the
  handshake advertises the same version, so a page can tell what it is talking to
  before its first call.
- **Reached through a grant, never wholesale.** Every operation belongs to one
  grant (`layers.read`, `layers.open`, `project.read`, `files.export`,
  `algorithms.read`, `algorithms.run`, `network.fetch`, ...), and the page is
  registered with `register_host_operations(only=...)`: what
  `[tool.qgis-sdk.web] grants` does not name is *absent* on this side too, so
  `host.settings` is `undefined` rather than a call that fails. The same names
  narrow the plugin's console (`[tool.qgis-sdk.console] grants`, every operation
  by default), and `qgis-sdk check --grants` prints the page/console matrix for
  one project. The complete list is
  [doc-22's host operations table](../../../backlog/docs/plans/doc-22%20-%20Service-coverage-map.md#host-operations).
- **A different vocabulary for the plugin's own actions.** The plugin HTTP API
  (`PluginHttpServer(actions=...)`) is the third authority-bearing client and it
  names **action and stream ids**, not host operations; there is no agent
  namespace to configure (decision-49 was withdrawn in 0.8.0).

### Features, expressions and editing from a page

`features.page` is a stream, not a call: the host asks the provider for one
bounded page, hands it over and waits, so a page that stops early has cost one
page rather than the dataset.

```ts
const subscription = await client.subscribe(
	"features.page",
	{ layer_id: "parcels", limit: 100, encoding: "geojson" },
	{
		onEvent: (event) => {
			const page = event.payload as FeaturePage;
			page.items.forEach(draw);
		},
		onTerminal: (terminal) => console.info("pages done:", terminal.kind),
	},
);
```

- **Each event is one `FeaturePage`**: `{items, truncated, next_cursor?}` where
  `next_cursor` is the last feature id of the page and `truncated` says more rows
  remain. The stream pages on by itself, so a consumer does not loop; `cursor` is
  optional and pins where it starts. A consumer that wants exactly one page opens
  the subscription and closes it after the first event, which costs the host one
  page rather than the layer.
- **Geometry is encoded, never an object graph.** `GeoJSON` text can be handed
  straight to a renderer, `wkb` is base64 of the provider's bytes for a consumer
  that stores them, `wkt` is text; `encoding` names which, and
  `geometry_type`/`crs`/`part_count`/`vertex_count`/`is_empty` describe it
  without a parser. A page asking for an encoding the source did not declare is
  refused by name.
- **`features.get`** returns one `Feature` in the same shapes, for a page that
  already has an id.
- **`expressions.evaluate` returns `ExpressionOutcome`**: `{valid, value?,
  message?}`. `valid: true` with `value: null` is a parsed expression whose value
  is null; `valid: false` with a message is a syntax or evaluation error. Neither
  is a failed call, so a console and a page see the same answer.
  `expressions.validate` returns `ExpressionCheck` with `referenced_columns`, for
  validating a form before anything runs.
- **Editing is a view-owned session.** `editing.begin({layer_id})` returns
  `{session_id, layer_id}`; `add`/`update`/`delete` return the pending count;
  `commit` returns `EditOutcome(applied, feature_ids, committed)` and `rollback`
  discards. The session belongs to the view that began it: an id from another
  view is refused as `unknown_handle`, and disposing the view closes every
  session it held.
- **No atomicity is promised.** `commit` reports `committed: false` or raises
  with the provider's message; the host never claims a transaction the provider
  does not have, and nothing here spans two layers. The tested boundaries per
  provider are in [doc-12](doc-12%20-%20qgis-sdk-Python-package-guide.md)'s
  editing section and in doc-22.

### Processing from a page: `algorithms.*` and `runAlgorithm`

The four `algorithms` operations
([decision-64](../../../backlog/decisions/decision-64%20-%20Generate-the-Processing-catalogue-from-the-host-registry-and-run-any-registered-algorithm-through-one-typed-surface.md))
expose the host's Processing registry behind two grants: `algorithms.read`
for `providers`, `list({provider?, limit?, cursor?})` and
`describe({algorithm_id})` - pages of `ProviderInfo` / `AlgorithmSummary`
and one `AlgorithmInfo` whose parameters carry `required`, `default_json`
(the default as JSON text, `null` when none), `options`, bounds and
`destination` - and `algorithms.run` for
`run({algorithm_id, params})`. The wire is generic JSON: `params` is the
map the algorithm's own description validates on the host before anything
runs, and the `RunResult` is a list of tagged outputs - `{name, kind:
"vector", layer}`, `{name, kind: "file", file}` or `{name, kind: "value",
value}`. A layer input is an owned layer id; a file input is a `FileRef`
this view holds, resolved against the view before the algorithm sees it;
a file the run produced comes back as a read-only `FileRef` minted for the
view. `HOST_FINGERPRINT` moved once for the four operations.

The typing lives next to the page, not in this package. `qgis-sdk
processing generate --web-out web/src/processing.schema.ts` (the scaffold's
`bindings` script runs it after `bridge generate`) renders, per algorithm,
`<Provider><Name>Params` and `<Provider><Name>Result`, an
`AlgorithmRegistry` keyed by id, and a `runAlgorithm` bound to it:

```ts
import { runAlgorithm } from "./processing.schema";

const { outputs } = await runAlgorithm(qgis, "native:buffer", {
	INPUT: layer.id,
	DISTANCE: 25,
});
outputs.OUTPUT; // VectorLayerInfo | undefined, as NativeBufferResult declares
```

Under it the root exports the generic pieces the generated module imports:
`runAlgorithm<R, K>(qgis, id, params, options?)` (sends one
`algorithms.run` and keys the tagged outputs by name), `outputsByName`,
`AlgorithmHost`, `AlgorithmRun<Result>`, `AlgorithmRegistryLike`, and the
value aliases `LayerRef`, `Destination` (`FileRef | null`: a page never
names a path), `Extent`, `PointValue` and `RangeValue`. A test scripts the
operation like any host id: `harness.expectInvoke("algorithms.run", (payload)
=> ({ algorithm: "native:buffer", outputs: [...] }))`. The scaffold writes
`web/src/processing.schema.ts` for `native` from the runtime's own snapshot
and grants `algorithms.run`; `bindings` regenerates it against the project's
QGIS, so a registry that differs shows up as drift rather than a stale type.

## The schema module and `QgisSdk`

`client.invoke<T>(...)` is a transport, not a type guarantee: `T` is asserted by
hand at the call site. For operations, generate the plugin's **schema module**
from its own declarations and build a `QgisSdk` on it
([decision-44](../../../backlog/decisions/decision-44%20-%20Generate-a-typed-bridge-schema-module-and-build-the-client-from-it-at-runtime.md)):

```console
$ qgis-sdk bridge generate --plugin my_plugin.plugin:app
wrote web/src/bridge.schema.ts
```

### What does the module export?

The module is data, not code. It exports the declared value types, `OPERATIONS`
and `OperationId`, one `Operations` interface (request and result per action),
one `Streams` interface (request and event union per stream), and as its
default export the parsed plugin description typed by both:

```ts
import { type BridgeSchema, defineBridgeSchema } from "@archont561/qgis-sdk";

export interface Operations {
	readonly "sites.summary": { readonly request: SitesSummaryRequest; readonly result: SitesSummaryResult };
	// ...
}
export interface Streams {
	readonly "sites.watch": { readonly request: SitesWatchRequest; readonly event: SitesWatchEvent };
}
const schema: BridgeSchema<Operations, Streams> = defineBridgeSchema<Operations, Streams>({ /* description */ });
export default schema;
```

### How does a page build a `QgisSdk`?

`defineBridgeSchema` is the module's only import. It parses and freezes the
description exactly as `parsePluginDescription` does and pins the two type
parameters; there is no generated validator, because the SDK validates at run
time from the schemas the description already carries. A page then needs
three statements:

```ts
import { QgisSdk } from "@archont561/qgis-sdk";
import schema from "./bridge.schema";

const qgis = QgisSdk.fromBridgeSchema(schema);
const summary = await qgis.sites.summary({ layer_id: "sites" });
```

### How does it connect, and what does it check?

#### Transport

Without options `fromBridgeSchema` connects to the `QWebChannel` object named
`"bridge"`, which is what the Python runtime registers on the view. Outside a
QGIS web view it throws `QgisSdkWebChannelError` (`code: "no_web_channel"`)
synchronously, so the page can say why instead of waiting on a channel that
never comes. Pass `{ transport }` to use another wire (the test harness below),
`{ client }` to share a `BridgeClient` the page already owns (then `close()`
leaves it alone), `{ channelObject }` for another registered name, `{ timeoutMs
}` for the per-call timeout of an owned client.

#### Compile time

Every declared operation is a method nested under the segments of its id:
`qgis.open_fixture()` for a plain id, `qgis.sites.summary(...)` for
`sites.summary`, `qgis.tools.measure.area(...)` for a deeper one - the same
shape as `qgis.host.layers.list(...)`. An operation the plugin did not declare
is not a member, and a misspelled or mistyped argument is a type error -
including an unknown property inside a nested object. An action whose request
declares no fields takes no argument. Two rules follow from nesting, checked by
`bridge generate` and again by `fromBridgeSchema` (`QgisSdkDeclarationError`):
an id may not be a prefix of another (`sites` cannot be a method and hold
`sites.summary`), and an id's first segment may not be a core member (`client`,
`host`, `schema`, `ready`, `close`).

#### Runtime

The method validates what it sends (strict: unknown arguments are refused
before the transport is touched) and what comes back (lenient: a field a newer
host added is tolerated, a missing or mistyped one is refused). Both refusals
are `QgisSdkContractError` (`code: "contract_validation_failed"`) naming the
operation, the direction (`request`, `result` or `event`) and the issues, each
with a path. Primitives, `list`/`tuple`, unions, `Literal` and nested
dataclasses are checked; a reply the schema cannot describe never reaches the
page.

#### Streams are operations too (decision-28)

A method the plugin marked with `@stream(id="sites.watch", events={"data":
SiteChange, "progress": ScanProgress})` becomes `qgis.sites.watch(request, {
onEvent, onTerminal }, options)`, returning the same `StreamHandle` as
`client.subscribe`. `onEvent` narrows on `event.kind`; a frame whose kind the
plugin did not declare, or whose payload does not match, ends the subscription
with an `error` terminal instead of reaching the handler. The frame envelope -
`seq`, `gap`, `close()` - stays in this package's kernel.

### What else is on the instance?

#### `qgis.host`

`qgis.host` is the typed host surface of [Host namespaces](#host-namespaces) on
the same client - `layers`, `project`, `settings`, `notifications`, `styles`,
`files` and the `network.fetch` stream - plus `granted`, the host operation ids
the handshake advertised for this view. A call outside the grants is refused by
the host with its own failure code; the SDK does not pre-empt it.

#### `qgis.ready`

`qgis.ready` resolves once the handshake answered; it rejects with the host's
`QgisSdkBridgeRemoteError` when the host refused the handshake and with
`QgisSdkBridgeProtocolError` when the reply is not a handshake; `qgis.client`
is the `BridgeClient` underneath for what no method covers; `qgis.schema` is
the module the instance was built from. A plugin may not declare an operation
named like one of these members (`QgisSdkDeclarationError`).

#### Owned by CI

The file is generated source, never edited by hand: the plugin's CI runs
`qgis-sdk bridge generate --check` and fails when the checked-in copy differs.
`CONTRACT_FINGERPRINT` identifies the wire contract the file was built from.

```ts
const handle = await qgis.sites.watch(
	{ layer_id: "sites" },
	{
		onEvent: (event) => {
			if (event.kind === "data") render(event.payload.change);
		},
		onTerminal: (terminal) => console.info("stream ended:", terminal.kind),
	},
);
```

### The 0.3.0 generated client

`qgis-sdk bridge generate --out web/src/bridge.ts` still renders what `0.3.0`
rendered - the import-free module with `createOperations(client)`,
`PluginOperations` and one validator per type - and prints a note that the
schema module is the current form. It stays for one minor. A page on the
legacy client keeps working unchanged.

## Stores: the framework-free core

A page's state is in four stores exported from the root, each a
`Store<T>`: `getSnapshot()` returns a stable, frozen snapshot and
`subscribe(listener)` calls the listener once synchronously and on every
change, returning an unsubscribe. Both are bound methods, so they can be
handed to `useSyncExternalStore`, a Svelte `$store` or a plain
`addEventListener`-style page unchanged. The stores import no framework and
no browser global; they are what the three adapters and the scaffold's vanilla
page are built on.

### Using the stores

```ts
import { QgisSdk, formStore, layersQuery } from "@archont561/qgis-sdk";
import schema from "./bridge.schema";

const qgis = QgisSdk.fromBridgeSchema(schema);

// A form over the declared `buffer` action: fields from the request schema.
const buffer = formStore(qgis, "buffer", { initial: { distance_metres: 500 } });
for (const field of buffer.fields) {
	// field.name, field.label ("Distance metres"), field.kind ("metres"),
	// field.required, field.choices, field.details ({ minimum, maximum, ... })
}
buffer.set("distance_metres", "750"); // strings are coerced per kind
buffer.subscribe((state) => {
	// state.values, state.issues, state.errors (first code per field),
	// state.valid, state.dirty, state.submitted, state.submission
});
await buffer.submit(); // validates first; an invalid form never calls the host

// A layer picker over the curated host surface, grant first.
const layers = layersQuery(qgis);
layers.subscribe((state) => {
	// idle | loading | ok (value: VectorLayerInfo[]) | error | refused
});
void layers.refresh();
```

### The four stores

Choose a store for an operation, stream, form or host query.

### `OperationStore(operation)`

One declared operation as state: `idle | pending | ok (value) | error (error)`.
`run(input)` resolves with the value or `undefined` (failed, aborted or
superseded; the state carries the error, so the promise never rejects into an
event handler); only the latest run can change the state. `abort()`, `reset()`.

### `StreamStore(open, handlers?)`

One subscription that follows the *content* of its input (`setInput(value)`,
keyed on `stableKey`; `null` closes it): `idle | opening | open | ended |
failed`. `setHandlers` swaps the callbacks without reopening; `close()` sends
one unsubscribe even before the host has acknowledged the open.

### `FormStore` / `formStore(qgis, actionId, { initial })`

The typed form for one declared action, built from its request schema with
`schemaFields(schema)`: a `FormField` per property with the parameter kind the
Python side marked (`"x-qgis-sdk"`,
[doc-12](doc-12%20-%20qgis-sdk-Python-package-guide.md)), a `labelFor` label,
`required`, `nullable`, `choices` and `details`. `set(name, value)` coerces
strings per kind (numbers, booleans, integers) and validates with
`validateAgainstSchema`; `setValues`, `reset()`, `submit()` (validates, marks
`submitted`, then runs the operation), `abort()`, `dispose()`, `field(name)`.
The declared dialect has no defaults, so starting values come from `initial`.

### `HostQueryStore(qgis, hostOperationId, loader)`

Reads the curated host surface after the handshake. When `qgis.host.granted`
lacks the operation the query needs it settles on `refused` (with the operation
id and a message) **without a call**, so a page can say "add `layers.read` to
the page's grants" instead of surfacing a `not_authorized` fault.
`layersQuery(qgis, { pageSize? })` follows `layers.list` to the last page;
`layerFieldsQuery(qgis, layerId)` reads `layers.get` for a `field` input whose
`of` names a layer input. Both need the `layers.read` grant, which the
scaffold's `[tool.qgis-sdk.web] grants` now lists.

### Misuse, and the shared behaviour suite

A `QgisSdkStoreError` (`"store_error"`) is raised for misuse: a form over an
action the schema does not declare, or a field the form does not have. The
behaviour suite in `tests/store-behaviour.ts` runs the same ten expectations
against the core and against each adapter's driver, so an adapter cannot
drift from the stores.

## React bindings

`./react` is an optional entry point ([decision-18](../../../backlog/decisions/decision-18%20-%20Ship-a-framework-neutral-bridge-and-explicit-web-scaffolding-choices.md)):
it is the only subpath that imports React, `react` is an optional peer, and
the root, `./bridge` and `./host` stay free of any framework or browser global
(`tests/surface.test.ts` bundles every entry and fails on a stray framework;
`tests/consumer/isolation.ts` walks `dist/` after every build and fails when
`./react` reaches `vue` or `svelte`, or the other way round). The bindings add
no second client and no behaviour of their own: every hook is
`useSyncExternalStore` over one of the [stores](#stores-the-framework-free-core).
A `BridgeProvider` shares the `QgisSdk` a vanilla page builds (or, for the
legacy client, its `BridgeClient`), and the hooks take the instance's methods,
so the typed contract is the generated one.

```ts
import { QgisSdk } from "@archont561/qgis-sdk";
import { BridgeProvider, useOperation, useQgisSdk, useStream } from "@archont561/qgis-sdk/react";
import schema, { type Operations, type Streams } from "./bridge.schema";

const qgis = QgisSdk.fromBridgeSchema(schema);

function App() {
	// Shares the instance the page owns; the provider never closes it. Pass
	// `transport` instead to let the provider own a client it closes on
	// unmount, or `client` to share a bare BridgeClient. Exactly one of the
	// three is required.
	return createElement(BridgeProvider, { qgis }, createElement(Sites));
}

function Sites() {
	const qgis = useQgisSdk<Operations, Streams>();
	const [summary, loadSummary] = useOperation(qgis.sites.summary);
	const watch = useStream(qgis.sites.watch, { layer_id: "sites" }, {
		onEvent: (event) => { if (event.kind === "data") render(event.payload.change); },
	});
	// summary.status: idle | pending | ok (value) | error (error)
	// watch.status:   idle | opening | open | ended (terminal) | failed (error)
}
```

`useOperations(createOperations)` remains for the 0.3.0 generated client and
is memoised per provider client, as before.

The form and the layer picker, as the React scaffold renders them:

```tsx
import { layersQuery } from "@archont561/qgis-sdk";
import { useForm, useHostQuery, useQgisSdk } from "@archont561/qgis-sdk/react";

function BufferForm() {
	const qgis = useQgisSdk<Operations, Streams>();
	const [state, form] = useForm(qgis, "buffer", { initial: { distance_metres: 500 } });
	const [layers] = useHostQuery(useMemo(() => layersQuery(qgis), [qgis]));
	// form.fields -> one <input> per declared field; form.set / form.submit
	// layers.status === "refused" -> tell the author which grant is missing
}
```

- **`useStore(store)`** subscribes a component to any `Store<T>`.
- **`useForm(qgis, actionId, options?)`** returns `[FormState, FormStore]`;
  the store is created once per `(qgis, actionId)` and aborted on unmount.
- **`useHostQuery(store, { auto? })`** returns `[HostQueryState, store]` and
  refreshes once on mount unless `auto: false`.

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
  disposes its subscriptions host-side ([decision-23](../../../backlog/decisions/decision-23%20-%20Adapt-Tauri-invocation-resource-and-testing-patterns-to-QWebChannel.md)).
  Unmounting a component under a live provider does send one.

## Vue bindings

`./vue` needs the optional `vue` peer (3.5 or later) and imports nothing else
of the framework family. It is the same stores through Vue's reactivity:

```ts
import { QgisSdk, layersQuery } from "@archont561/qgis-sdk";
import { provideQgisSdk, useForm, useHostQuery, useOperation, useQgisSdk, useStream } from "@archont561/qgis-sdk/vue";

// In the root component's setup():
provideQgisSdk(QgisSdk.fromBridgeSchema(schema));

// In any descendant's setup():
const qgis = useQgisSdk<Operations, Streams>();
const summary = useOperation(qgis.sites.summary); // { state, run, abort, reset, store }
const watch = useStream(qgis.sites.watch, () => input.value, { onEvent }); // input: Ref<I | null>
const { state, form } = useForm(qgis, "buffer", { initial: { distance_metres: 500 } });
const { state: layers, query } = useHostQuery(layersQuery(qgis));
```

Every `state` is a read-only `ShallowRef` (`useStore(store)` gives one for any
store); `useStream` takes a `MaybeRefOrGetter<I | null>` and follows it with
`watch(..., { immediate: true })`; disposing the effect scope (unmounting)
aborts the operations and closes the streams the component opened.
`provideQgisSdk` outside `setup()` and `useQgisSdk` without a provider raise
`QgisSdkBridgeVueError` (`"vue_binding"`). `QGIS_SDK_KEY` is the injection
key, for a page that prefers `provide`/`inject` by hand.

## Svelte bindings

`./svelte` needs the optional `svelte` peer (5 or later). The stores already
satisfy Svelte's store contract, so a component reads them as `$store`; the
adapter adds the context and the `onDestroy` wiring:

```svelte
<script lang="ts">
	import { layersQuery } from "@archont561/qgis-sdk";
	import { form, getQgisSdk, hostQuery, operation, stream } from "@archont561/qgis-sdk/svelte";

	// The root component called setQgisSdk(QgisSdk.fromBridgeSchema(schema)).
	const qgis = getQgisSdk<Operations, Streams>();
	const summary = operation(qgis.sites.summary); // aborted on destroy
	const watch = stream(qgis.sites.watch, { onEvent }); // watch.setInput(...)
	const buffer = form(qgis, "buffer", { initial: { distance_metres: 500 } });
	const layers = hostQuery(layersQuery(qgis)); // refreshed once, closed on destroy
</script>

{#if $layers.status === "refused"}<p>{$layers.message}</p>{/if}
{#each buffer.fields as field}<label>{field.label} <input on:input={(e) => buffer.set(field.name, e.currentTarget.value)} /></label>{/each}
<p>{$buffer.valid ? "" : Object.values($buffer.errors).join(", ")}</p>
```

`toRune(store)` returns `{ current }` backed by `$state` for a runes-mode
component that prefers it to `$store`. `setQgisSdk`/`getQgisSdk` outside
component initialisation raise `QgisSdkBridgeSvelteError`
(`"svelte_binding"`); `QGIS_SDK_CONTEXT` is the context key.

## Components: `@archont561/qgis-sdk-ui`

The web half of the UI catalogue (decision-55) is a second npm package,
`@archont561/qgis-sdk-ui` ([decision-47](../../../backlog/decisions/decision-47%20-%20Build-web-UI-on-a-framework-free-store-core-with-per-framework-adapters-and-ship-components-as-qgis-sdk-ui.md)
point 3). It peer-depends on this package through a caret range,
has `lit` as its only dependency, and ships `dist`, `README.md` and
`LICENSE` - nothing else (a pack test keeps it so). Like this package it
has an unscoped alias, `qgis-sdk-ui` (`packages/qgis-sdk-ui-alias`), that
re-exports every entry and `@import`s both stylesheets at the exact same
version; a `ui-v*` tag publishes the pair.

### The elements

Every element is a Lit element rendering into **itself** - no shadow root -
so the page's stylesheet reaches each control, a `<label for>` works, and
`querySelector` finds what a test or a script needs. Each carries
`data-qgis-sdk="<name>"` on the host element and `data-part` hooks inside
(`label`, `control`, `error`, and per element `pick`, `cancel`, `clear`);
an error renders as `data-part="error"` and is `aria-describedby` from the
control.

| Element | Mirrors (native) | Reads | Raises |
| --- | --- | --- | --- |
| `<qgis-form>` | `Form` | `.store` (a `FormStore`), `.qgis`, `.pickers`, `submit-label` | `qgis-change`, `qgis-run`, `qgis-result` |
| `<qgis-layer-picker>` | `LayerPicker` | `.qgis`, `geometry`, `nullable`, `required` | `qgis-change` |
| `<qgis-field-picker>` | `FieldPicker` | `.qgis`, `.layer` or `.of` (a layer picker to follow), `nullable`, `required` | `qgis-change` |
| `<qgis-crs-picker>` | `CrsPicker` | `.suggestions`, `.value`, `required` | `qgis-change` |
| `<qgis-distance>` | `Distance` | `unit`, `.min`, `.max`, `.step`, `.value`, `required` | `qgis-change` |
| `<qgis-choice>` | `Choice` | `.options` (alias `.choices`), `.value`, `nullable`, `required` | `qgis-change` (typed value) |
| `<qgis-file-input>`, `<qgis-directory-input>` | `FileInput`, `DirectoryInput` | `.pick` (a `FileRef` picker), `.filters`, `.value`, `required` | `qgis-change` (a `FileRef` or `null`) |
| `<qgis-job-progress>` | `JobProgress` | `status`, `.fraction`, `message`, `.store`, `.cancel`, `cancellable` | `qgis-cancel` |
| `<qgis-log-view>` | `LogView` | `.lines`, `limit`, `.store`, `clearable` | - |
| `<qgis-run-button>` | `RunButton` | `.form` or `.operation` + `.input`, `text` (alias of `label`), `pending-label` | `qgis-run`, `qgis-result` |

#### The keyword forms, both spellings

A component reads the same in Python and in a page for the names both
catalogues have. The Python keyword is the constructor
argument of `qgis_sdk.ui`; the web spelling is the element property (the
`.prop` binding in Lit, the prop of a wrapper), with the attribute where one
exists. What one side has and the other does not is said so, not papered
over.

| Component | Python keyword | Web property | Note |
| --- | --- | --- | --- |
| every input | `name=` | `name` | the field name; `data-qgis-sdk` on the web, `objectName` `form/<name>` natively |
| every component | `label=` | `label` | derived from the name natively; empty renders none on the web |
| every input | `required=` | `required` | the control gets `required`/`aria-required` on the web; `Form.submit()` refuses an empty required field natively |
| every input | `value=` | `.value` | same shape as the wire model (`FileRef`, `AUTHORITY:CODE`, the typed choice) |
| - | - | `disabled`, `error`, `nullable`, `placeholder` | web only: the page's own state; a native component is disabled through its widget, an error is the form's |
| `Choice` | `options=` | `.options` | `.choices` stays as an alias |
| `LayerPicker` | `kind=` (`vector`/`raster`/`any`) | - | the web picker lists vector layers; `geometry` (web only) narrows by geometry type |
| `FieldPicker` | `of=<LayerPicker>` | `.of=${picker}` or `.layer="<id>"` | `of` follows the picker's `qgis-change`; `layer` takes the id directly |
| `FileInput` | `filters=` | `.filters` | the same glob strings |
| `Distance` | - | `unit`, `.min`, `.max`, `.step` | natively a `Distance` is metres with the host's spin box; the web input says its unit |
| `JobProgress` | `cancellable=` | `cancellable` | the web button also needs a `.cancel` callback to call |
| `LogView` | `limit=` | `limit` | `clearable` (web) is `clear()` (native) |
| `Button`/`RunButton` | `text=` | `text` (alias of `label`) | the caption |
| `RunButton` | `action_id=`, `values=`, `progress=` | `.form` or `.operation` + `.input` | the web button runs a store; the native one dispatches an action id through `ctx.actions` |
| `Form` | `fields=`, `action_id=` | `.store` (`formStore(qgis, actionId)`) | the web form reads its fields from the action's schema in the store |

A wrapper (`./react`, `./vue`, `./svelte`) forwards every property above;
`ELEMENT_PROPS` in the package lists them per tag and a test keeps it equal
to the elements' reactive properties.

`import "@archont561/qgis-sdk-ui/define"` registers the whole catalogue
(`DEFINED` lists what it registered); `defineElements(registry?)` from the
root does the same on demand and leaves a tag another script took. The
host-bound pickers are `layersQuery` and `layerFieldsQuery` behind an element:
without the `layers.read` grant they show the refusal and its remedy, and a
host fault lands under the control as `data-part="error"`. A page never
names a path: a file input holds a host-minted `FileRef` and shows its
`name`.

### Styling: `style.css`, the tokens and `./uno`

Two stylesheets ship. `tokens.css` sets the `--qgis-sdk-*` custom
properties - the light defaults on `:root`, the dark ones under
`[data-qgis-sdk-theme="dark"]`. `style.css` is compiled from the package's
own sources by UnoCSS `preset-mini` with every utility `qs-` prefixed and
**no preflight**, so it sits beside a page's Tailwind or Uno classes without
a selector in common (a collision fixture proves it), and every colour, font
and radius in it is a `var(--qgis-sdk-*)` - a palette change is a variable
change, never a rebuild. The build refuses a `style.css` over its documented
byte budget.

The tokens (`TOKEN_NAMES`) are the theme surface decision-16 names: `bg`,
`fg`, `surface`, `surface-fg`, `control`, `control-fg`, `accent`,
`accent-fg`, `border`, `muted`, `link`, `danger`, `font`, `font-size`,
`radius`, `space`. `applyHostTheme(qgis)` waits for the handshake, maps the
host palette's roles onto them (`PALETTE_ROLES`: `window` → `bg`,
`highlight` → `accent`, ...) over the matching light or dark defaults, sets
them on `<html>` and `data-qgis-sdk-theme`; outside QGIS it resolves `null`
and the stylesheet defaults stay. `applyTheme(tokens)`, `clearTheme()`,
`tokensFromTheme(theme)` and `tokensStylesheet()` are the pieces.

A page that runs UnoCSS itself imports the preset instead of the
stylesheet: `presetQgisSdk()` from `./uno` (peer `@unocss/preset-mini`)
builds the same `qs-` utilities over the same token colours in the
consumer's own pipeline.

### Wrappers

`./react` wraps every element with `@lit/react` (`QgisForm`,
`QgisLayerPicker`, ... with `onChange`, `onRun`, `onResult`, `onCancel`
props and a `ref` to the element); `./vue` exports components that bind
every prop as a property and re-emit `change`, `result`, `run` and `cancel`,
plus a `components` map for `app.component`; `./svelte` needs no wrapper -
Svelte 5 sets properties on a registered element - and exports `ON` (the
event attribute names) and the `use:qgisProps={props}` action for a
`<svelte:element>`. All three pass one behaviour suite
(`tests/wrapper-behaviour.ts`).

### Storybook and the stories as fixtures

`bun run storybook` (in `packages/qgis-sdk-ui`) builds the package and
serves the catalogue; `bun run storybook:build` writes `storybook-static/`,
which CI builds on every run (`pixi run -e bun storybook-build`) and the docs
workflow publishes at
[archont561.github.io/qgis-sdk/storybook/](https://archont561.github.io/qgis-sdk/storybook/).
The toolbar's **Theme** entry
switches the QGIS light and dark palettes through the tokens, the a11y addon
runs with `test: "error"`, and every story renders against
`createBridgeHarness` - "Refused" and "Faulted" are states of a component,
not broken stories. The same stories are fixtures: `tests/stories.test.ts`
composes them with `composeStories` under the preview's annotations and
checks, per story, light-DOM rendering, the hooks, label-to-control
association and, for the form, that the focus order follows the declaration
and ends on the run button.

Inside QGIS the page's variables match the running palette: the WebEngine
harness (`QGIS_SDK_SCAFFOLD_WEB=1`, `test_scaffold_web_native.py`) loads the
scaffolded Tier 1 pages, which call `applyHostTheme(qgis)` on start, and
after the ping reads the document's computed `--qgis-sdk-bg` and
`--qgis-sdk-fg` back: they equal the `window` and `windowText` colours
`palette_theme()` read from the running `QApplication`, and
`data-qgis-sdk-theme` says which side the defaults came from.

## Testing against a scripted host

`./testing` is a `WireTransport` a test hands to `QgisSdk.fromBridgeSchema`
(or to its own `BridgeClient`), so the page's real client, the SDK's contract
validation and the React bindings all run unchanged against a host the test
scripts. Nothing global is mutated: two harnesses are two hosts, and a test
can prove nothing crosses between their clients.

```ts
import { QgisSdk } from "@archont561/qgis-sdk";
import { SILENCE, createBridgeHarness, fault } from "@archont561/qgis-sdk/testing";
import schema from "./bridge.schema";

const harness = createBridgeHarness(schema); // expectations typed by the schema
const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });

harness.expectInvoke("sites.summary", (payload) => ({ total: 1, largest: payload.layer_id, mode: "fast" }));
harness.expectInvoke("sites.summary", () => fault("forbidden", "not yours"));
harness.expectInvoke("sites.summary", () => SILENCE); // the client's own timeout speaks
harness.expectSubscribe("sites.watch", (_payload, stream) => {
	stream.emit("data", { change: "added" });
	stream.skip(2); // the next frame is a gap, ended the way the kernel promises
	stream.end({ kind: "complete" });
});

await qgis.sites.summary({ layer_id: "sites" });
harness.calls;      // every envelope the client sent, in order; the handshake first
harness.assertSatisfied(); // unmet expectations, unexpected calls, open subscriptions, handler throws
```

- **Handshake.** A harness built on a schema answers the SDK's handshake by
  itself, from the schema and `HOST_OPERATIONS`; `createBridgeHarness(schema,
  { granted: ["layers.list"] })` narrows what `qgis.host.granted` reports, for
  tests of a page under a restricted host. The handshake is recorded in
  `harness.calls` with `kind: "handshake"`; filter it out when asserting the
  operations a page made.
- **Untyped form.** `createBridgeHarness<OperationId>()` without a schema is
  what the 0.3.0 generated client and bare `BridgeClient` tests use;
  `expectInvoke<Req, Res>` then takes the types by hand.

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

## 0.6.0 migration notes

**Two bridge error classes are gone.** `QgisSdkBridgeSequenceError` and
`QgisSdkBridgeStreamEndedError` left the `./bridge` entry: no code path
constructed either, because a missed frame arrives as the stream
terminal's `{ kind: "gap" }` and an end as its terminal frame. Switch on
the terminal's `kind`, as the [stores](#stores-the-framework-free-core)
already do, and drop any `instanceof` checks for the two.

**Deeper module paths stay internal.** The entry split into
`src/bridge/{client,errors,frames,protocol}.ts` and
`src/stores/{base,form,host-query,operation,stream}.ts` behind the same
`@archont561/qgis-sdk/bridge`, `./react`, `./vue` and `./svelte` exports,
so an import from the package keeps working; a deep import into `src/`
was never public.

**The wire is unchanged.** `HOST_FINGERPRINT` (`sha256:16790dc8...`),
`HOST_SCHEMA_VERSION` (1) and `BRIDGE_PROTOCOL_VERSION` (1) carry the
values 0.5.0 had, so a page built against a 0.5 host needs no edit. The
Python side of the same release is in
[doc-12](doc-12%20-%20qgis-sdk-Python-package-guide.md) under *Next minor
(unreleased) migration notes*.

## 0.5.0 migration notes


**`@archont561/qgis-sdk-ui` 0.1.0 (decision-47 point 3).** A new
package rather than a change to this one; see
[Components](#components-archont561qgis-sdk-ui). This package gains nothing
for it except being its peer. `qgis-sdk new --web` opts in through one import
(`--ui-dependency` pins it); `release.py` knows the `ui` scope and refuses a
UI release whose bridge peer range excludes the workspace bridge.
0.1.0 adds the Python keyword spellings to the elements (`.options` on
`<qgis-choice>` with `.choices` as the alias, `required` on every input,
`cancellable` on `<qgis-job-progress>`, `text` on `<qgis-run-button>`,
`.of` on `<qgis-field-picker>`); nothing existing changed meaning.

**Processing from a page (decision-64).** Four new host operations
(`algorithms.providers/list/describe/run`) and two grants (`algorithms.read`,
`algorithms.run`) move `HOST_FINGERPRINT` to `sha256:16790dc8…`;
`HOST_SCHEMA_VERSION` and `BRIDGE_PROTOCOL_VERSION` stay at 1. `./host` also
exports the new shapes (`AlgorithmInfo`, `AlgorithmSummary`,
`ParameterInfo`, `OutputInfo`, `ProviderInfo`, `RunOutput`, `RunResult`,
their request types) and the root exports `runAlgorithm`, `outputsByName`
and the Processing value aliases. A bare `{"type": "object"}` in a
declaration now renders as `Record<string, unknown>` instead of an empty
interface. `qgis-sdk new --web` writes `web/src/processing.schema.ts`,
grants `algorithms.run` and extends the `bindings` script with
`qgis-sdk processing generate --check`; an existing project adds the file
with that command and the grant by hand.

**Stores and two more adapters (decision-47).** The root now exports
the four stores; `./react` is rewritten over them with the same exported names
and types (`react.test.ts` passes unchanged) plus `useStore`, `useForm` and
`useHostQuery`; `./vue` and `./svelte` are new subpaths behind optional peers.
A `./react`-only consumer's bundle gains no Vue or Svelte code. The scaffold's
web templates render a form from the declaration and a layer picker over
`layers.list`, so `qgis-sdk new --web` now writes
`grants = ["layers.read"]` into `[tool.qgis-sdk.web]`; an existing project
that adopts `layersQuery` adds that grant by hand or sees the store's
`refused` state.

**Parameter kinds on the wire (decision-46 point 1).** A declared
input the Python side marked (`LayerInput`, `FileInput(filters=)`,
`Range(min, max)`, ...) carries `"x-qgis-sdk": { kind, ...attributes }` in its
request schema. `validateAgainstSchema` reads past the keyword (any other
`x-` keyword is still refused), a regenerated `bridge.schema.ts` documents
each such field with `/** @qgis-sdk-kind <kind> */` and its
`CONTRACT_FINGERPRINT` moves - regenerate it with `qgis-sdk bridge generate`.
`FileRef.kind` is now `"file" | "directory"` (`HostAuthority.grant_directory`
mints the latter), so `HOST_FINGERPRINT` moved to `sha256:af91deac…`;
`HOST_SCHEMA_VERSION` and `BRIDGE_PROTOCOL_VERSION` stay at 1. A page passes
the `FileRef` it received from the host where an action declares
`FileInput()`; the Python handler receives it as a `FileRef`.

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

## 0.3.0 migration notes

`0.3.0` is a rename release (`ts-v0.3.0`): the exports of `0.2.0` under the
new name, plus the unscoped alias. Verify with
`python scripts/release.py verify-versions --scope typescript --version 0.3.0`.

- **Package renamed.** `@archont561/qgis-sdk-bridge` is now
  `@archont561/qgis-sdk`, published first as `0.3.0` with the exports of
  `0.2.0` unchanged ([decision-33](../../../backlog/decisions/decision-33%20-%20Rename-the-npm-package-to-archont561-qgis-sdk-and-suffix-the-package-directories.md)).
  Replace the dependency and the import specifiers; the subpaths keep their
  names (`@archont561/qgis-sdk/bridge`, `/host`, `/react`, `/testing`). The
  old name stays installable and is deprecated on npm with a pointer here.
- **Unscoped alias.** `qgis-sdk` on npm is a thin alias of
  `@archont561/qgis-sdk` (same version, exact pin, one `export *` per entry),
  published by the same release job right after the scoped package. The
  `0.0.0` placeholder each name carries exists only so npm trusted publishing
  could be configured; install `>= 0.3.0`.
- **Repository layout.** The source moved from `packages/qgis-sdk-bridge` to
  `packages/qgis-sdk-typescript`; the Python package moved from
  `packages/qgis-sdk` to `packages/qgis-sdk-python`. Only contributors and
  the generated-file paths in CI are affected.

## 0.4.0 migration notes

`0.4.0` is unreleased at the time of writing; it is the root-entry change of
[decision-40](../../../backlog/decisions/decision-40%20-%20Make-the-root-entry-the-page-import-and-keep-generated-plugin-clients-import-free.md)
on `main`, paired with Python `0.6.0`. Neither the transport protocol (`1`),
the plugin-description contract (`1`), `HOST_SCHEMA_VERSION` nor
`HOST_FINGERPRINT` moves: what crosses `QWebChannel` is identical.

- **`QgisSdk.fromBridgeSchema(schema)` replaces the generated client
  ([decision-44](../../../backlog/decisions/decision-44%20-%20Generate-a-typed-bridge-schema-module-and-build-the-client-from-it-at-runtime.md)).**
  `qgis-sdk bridge generate` now writes `web/src/bridge.schema.ts`, a module
  with types and the parsed description and no validators; the SDK validates
  at run time. The hand-written `QWebChannel` glue the 0.3.0 scaffold put in
  `web/src/transport.ts` is in the package. The reference example's
  `main.ts`, before and after:

  ```ts
  // 0.3.0
  import { BridgeClient } from "@archont561/qgis-sdk/bridge";
  import { createApp } from "./app";
  import { createOperations } from "./bridge";
  import { connectWebChannel, insideQgis } from "./transport";

  if (insideQgis()) {
    connectWebChannel().then(
        (transport) => createApp(root, createOperations(new BridgeClient(transport))),
        (failure: unknown) => { root.textContent = String(failure); },
    );
  } else {
    root.textContent = "Open this page from QGIS.";
  }
  ```

  ```ts
  // 0.4.0
  import { QgisSdk } from "@archont561/qgis-sdk";
  import { createApp } from "./app";
  import schema from "./bridge.schema";

  const qgis = QgisSdk.fromBridgeSchema(schema);
  createApp(root, qgis);
  ```

  Methods nest by the dots in the declared id exactly as the 0.3.0 client's
  did (`operations.sites.summary(...)` becomes `qgis.sites.summary(...)`,
  `operations.buffer(...)` becomes `qgis.buffer(...)`). Point the `bindings`
  script at `--out web/src/bridge.schema.ts --check`, delete `transport.ts`
  and the old `bridge.ts`, and pass the instance where
  `createOperations(client)` was passed; in tests, `createBridgeHarness(schema)`
  plus `QgisSdk.fromBridgeSchema(schema, { transport: harness })`. The
  `--out web/src/bridge.ts` form keeps rendering the 0.3.0 client for one
  minor with a deprecation note. `qgis-sdk new --web` from tools `0.6.0`
  writes the three-statement page; its pinned bridge moves to `0.4.0` in the
  same release stamp (decision-41).
- **The handshake answers from the dispatcher.** A page's first envelope may
  be `kind: "handshake"`; a Python `0.6.0` host answers it with the protocol,
  generation, plugin description and the host operation ids this view may
  call. Protocol `1` is unchanged: a `0.5.0` host refuses the same envelope
  with `invalid_message`, so `qgis.ready` rejects with that
  `QgisSdkBridgeRemoteError` and `qgis.host.granted` stays empty; the
  declared methods still work against it.
- **The root re-exports `./bridge`.** `import { BridgeClient } from
  "@archont561/qgis-sdk"` works; the `./bridge` subpath is unchanged and
  remains the import of existing code. `./host`, `./react` and `./testing`
  stay subpath-only.
- **Removed from the root:** `QgisSdkScopeClosedError` and
  `QgisSdkUnsupportedCapabilityError` (never raised by this package; the
  Python error arrives as a `QgisSdkBridgeRemoteError` whose `code` is
  `scope_closed` or `unsupported_capability`) and `isPlainRecord` (an
  internal helper; write the three-line guard locally if you relied on it).
- **Generated errors renamed, with a code.** `./host` exports
  `QgisSdkHostContractError` (was `HostContractError`), now a `QgisSdkError`
  with `code: "contract_validation_failed"`. A plugin client regenerated with
  `qgis-sdk bridge generate` from tools `0.6.0` exports
  `QgisSdkContractError` (was `ContractError`), still a plain `Error`, with
  the same `code`. Replace the names in `catch` clauses and prefer matching
  on `error.code`.
- **Manifest:** stays `0.3.0` until the release gate stamps it. Verify a
  stamped pair with
  `python scripts/release.py verify-versions --scope typescript --version 0.4.0`.
