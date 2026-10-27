/**
 * `QgisSdk.fromBridgeSchema` (TASK-66 AC #2, #3 and #5), on the schema module
 * generated from the sample plugin and the scripted harness as its transport.
 *
 * What is proven: one method per declared operation, nested under the
 * segments of its id and checked against the declaration on both sides; the host surface on the same client
 * with `granted` read from the handshake; ownership of the client. What is
 * not: a QWebChannel - that is `webchannel.test.ts`, against a fake channel.
 */

import { expect, test } from "@archont561/bun-test-utils";
import { BridgeClient, QgisSdkBridgeRemoteError } from "../src/bridge";
import { QgisSdkDeclarationError } from "../src/declarations";
import { HOST_OPERATIONS } from "../src/generated/host";
import {
	QGIS_SDK_MEMBERS,
	QgisSdk,
	type StreamHandlers,
} from "../src/qgis-sdk";
import { defineBridgeSchema } from "../src/schema";
import {
	type BridgeHarness,
	createBridgeHarness,
	fault,
	type ScriptedStream,
} from "../src/testing";
import { QgisSdkContractError } from "../src/validate";
import { QgisSdkWebChannelError } from "../src/webchannel";
import schema, {
	CONTRACT_FINGERPRINT,
	OPERATIONS,
	PLUGIN_ID,
	type SitesWatchEvent,
} from "./contracts/generated/clients/sites.schema";

const SUMMARY = { total: 3, largest: "B", mode: "fast" } as const;

test("the generated schema module is the parsed description plus its constants", () => {
	expect(PLUGIN_ID).toBe("org.example.sites");
	expect(CONTRACT_FINGERPRINT).toMatch(/^sha256:[0-9a-f]{64}$/);
	expect(OPERATIONS).toEqual([
		"sites.details",
		"sites.refresh",
		"sites.summary",
		"sites.watch",
	]);
	expect(schema.id).toBe(PLUGIN_ID);
	expect(schema.actions.map((action) => action.id)).toEqual([
		"sites.details",
		"sites.refresh",
		"sites.summary",
	]);
	expect(schema.streams.map((stream) => stream.id)).toEqual(["sites.watch"]);
	expect(Object.isFrozen(schema)).toBe(true);
});

test("defineBridgeSchema refuses what parsePluginDescription refuses", () => {
	expect(() => defineBridgeSchema({ schema_version: 2 })).toThrow(
		QgisSdkDeclarationError,
	);
	expect(() => defineBridgeSchema("{not json")).toThrow(
		QgisSdkDeclarationError,
	);
});

test("an instance nests one method per declared operation under its dotted id", () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	// Every id here is `sites.<leaf>`, so the instance has the core members
	// and one namespace; the namespace has one method per leaf.
	expect(Object.keys(qgis).sort()).toEqual(
		[...QGIS_SDK_MEMBERS, "sites"].sort(),
	);
	expect(Object.keys(qgis.sites).sort()).toEqual(
		OPERATIONS.map((id) => id.slice("sites.".length)).sort(),
	);
	expect(typeof qgis.sites.summary).toBe("function");
	expect(typeof qgis.sites.watch).toBe("function");
	expect(qgis.schema).toBe(schema);
	expect(qgis.client).toBeInstanceOf(BridgeClient);
	expect(Object.isFrozen(qgis)).toBe(true);
	expect(Object.isFrozen(qgis.sites)).toBe(true);
	expect("sites.summary" in qgis).toBe(false);
	expect("relfresh" in qgis.sites).toBe(false);
	qgis.close();
});

test("a plain id is a method on the instance, a deeper id nests further", () => {
	const mixed = defineBridgeSchema({
		schema_version: 1,
		id: "demo",
		title: "Demo",
		actions: [
			describeAction("ping"),
			describeAction("tools.measure.length"),
			describeAction("tools.measure.area"),
			describeAction("tools.reset"),
		],
	});
	const qgis = QgisSdk.fromBridgeSchema(mixed, {
		transport: createBridgeHarness(mixed),
	});
	const members = qgis as unknown as Record<string, unknown>;
	expect(typeof members.ping).toBe("function");
	const tools = members.tools as Record<string, unknown>;
	const measure = tools.measure as Record<string, unknown>;
	expect(Object.keys(tools).sort()).toEqual(["measure", "reset"]);
	expect(Object.keys(measure).sort()).toEqual(["area", "length"]);
	expect(typeof measure.length).toBe("function");
	expect(Object.isFrozen(measure)).toBe(true);
	qgis.close();
});

test("an id may not be both an operation and a namespace of other ids", () => {
	for (const ids of [
		["sites", "sites.summary"],
		["sites.summary", "sites"],
		["a.b.c", "a.b"],
	]) {
		const colliding = defineBridgeSchema({
			schema_version: 1,
			id: "demo",
			title: "Demo",
			actions: ids.map((id) => describeAction(id)),
		});
		expect(() =>
			QgisSdk.fromBridgeSchema(colliding, {
				transport: createBridgeHarness(),
			}),
		).toThrow(QgisSdkDeclarationError);
	}
});

test("an id with an empty segment is refused before anything is built", () => {
	const empty = defineBridgeSchema({
		schema_version: 1,
		id: "demo",
		title: "Demo",
		actions: [describeAction("sites..summary")],
	});
	expect(() =>
		QgisSdk.fromBridgeSchema(empty, { transport: createBridgeHarness() }),
	).toThrow(QgisSdkDeclarationError);
});

function describeAction(id: string) {
	return {
		id,
		title: id,
		handler: "run",
		request: { type: "object", properties: {}, additionalProperties: false },
		result: { type: "null" },
	};
}

test("a call sends the declared id with the checked request and returns the checked result", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	harness.expectInvoke("sites.summary", (payload) => {
		expect(payload).toEqual({ layer_id: "sites", mode: "fast" });
		return SUMMARY;
	});
	const result = await qgis.sites.summary({
		layer_id: "sites",
		mode: "fast",
	});
	expect(result).toEqual(SUMMARY);
	expect(result.total).toBe(3);
	expect(harness.calls.map((call) => `${call.kind} ${call.operation}`)).toEqual(
		["handshake ", "invoke sites.summary"],
	);
	harness.assertSatisfied();
	qgis.close();
});

test("an empty request may be omitted and is sent as an empty object", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	harness.expectInvoke("sites.refresh", (payload) => {
		expect(payload).toEqual({});
		return SUMMARY;
	});
	await qgis.sites.refresh();
	harness.assertSatisfied();
	qgis.close();
});

test("a request outside the schema never reaches the transport", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const bad = [
		{ layer_id: 7 },
		{ layer_id: "sites", limit: 1.5 },
		{ layer_id: "sites", mode: "slow" },
		{ layer_id: "sites", label: 1 },
		{ layer_id: "sites", guess: true },
		{},
		"sites",
		null,
	];
	for (const request of bad) {
		const failure = await qgis.sites.summary(request as never).then(
			() => null,
			(error: unknown) => error,
		);
		expect(failure).toBeInstanceOf(QgisSdkContractError);
		const error = failure as QgisSdkContractError;
		expect(error.code).toBe("contract_validation_failed");
		expect(error.direction).toBe("request");
		expect(error.operation).toBe("sites.summary");
		expect(error.issues.length).toBeGreaterThan(0);
	}
	// A nested dataclass is checked by path.
	const nested = await qgis.sites
		.details({
			layer_id: "sites",
			options: { limit: "1" } as never,
		})
		.then(
			() => null,
			(error: unknown) => error as QgisSdkContractError,
		);
	expect(nested?.issues.map((issue) => issue.path)).toEqual([
		["options", "limit"],
	]);
	// `X | None` and Literal are accepted as declared.
	harness.expectInvoke("sites.summary", () => SUMMARY);
	await qgis.sites.summary({
		layer_id: "sites",
		label: null,
		mode: "exact",
	});
	expect(harness.calls.filter((call) => call.kind === "invoke")).toHaveLength(
		1,
	);
	harness.assertSatisfied();
	qgis.close();
});

test("a reply outside the schema is a result contract error, extra fields are not", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	harness.expectInvoke("sites.summary", () => ({ total: "3" }) as never);
	const failure = await qgis.sites.summary({ layer_id: "sites" }).then(
		() => null,
		(error: unknown) => error as QgisSdkContractError,
	);
	expect(failure).toBeInstanceOf(QgisSdkContractError);
	expect(failure?.direction).toBe("result");
	expect(
		failure?.issues.map((issue) => `${issue.path.join(".")}:${issue.code}`),
	).toEqual(["largest:required", "mode:required", "total:type"]);
	harness.expectInvoke(
		"sites.summary",
		() => ({ ...SUMMARY, since: "0.5.0" }) as never,
	);
	const extended: unknown = await qgis.sites.summary({ layer_id: "sites" });
	expect(extended).toEqual({ ...SUMMARY, since: "0.5.0" });
	harness.assertSatisfied();
	qgis.close();
});

test("a host failure surfaces as the remote error with its code", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	harness.expectInvoke("sites.summary", () =>
		fault("operation_failed", "no such layer"),
	);
	const failure = await qgis.sites.summary({ layer_id: "x" }).then(
		() => null,
		(error: unknown) => error,
	);
	expect(failure).toBeInstanceOf(QgisSdkBridgeRemoteError);
	expect((failure as QgisSdkBridgeRemoteError).failure.code).toBe(
		"operation_failed",
	);
	qgis.close();
});

test("a stream delivers declared events typed by kind and ends once", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	let scripted: ScriptedStream | null = null;
	harness.expectSubscribe("sites.watch", (payload, stream) => {
		expect(payload).toEqual({ layer_id: "sites", every_ms: 10 });
		scripted = stream;
	});
	const events: SitesWatchEvent[] = [];
	const terminals: string[] = [];
	const handlers: StreamHandlers<SitesWatchEvent> = {
		onEvent: (event) => {
			events.push(event);
			if (event.kind === "data") {
				expect(event.payload.change).toBe("added");
			} else {
				expect(event.payload.done).toBe(1);
			}
		},
		onTerminal: (terminal) => terminals.push(terminal.kind),
	};
	const handle = await qgis.sites.watch(
		{ layer_id: "sites", every_ms: 10 },
		handlers,
	);
	const open = scripted as ScriptedStream | null;
	if (open === null) {
		throw new Error("the harness did not open the stream");
	}
	open.emit("data", { layer_id: "sites", change: "added", count: 1 });
	open.emit("progress", { done: 1, total: 2 });
	open.end({ kind: "complete" });
	await harness.settled();
	expect(events.map((event) => event.kind)).toEqual(["data", "progress"]);
	expect(terminals).toEqual(["complete"]);
	expect(handle.closed).toBe(true);
	harness.assertSatisfied();
	qgis.close();
});

test("an event outside the declared events ends the stream with an error terminal", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	let scripted: ScriptedStream | null = null;
	harness.expectSubscribe("sites.watch", (_payload, stream) => {
		scripted = stream;
	});
	const terminals: { kind: string; message?: string }[] = [];
	const events: unknown[] = [];
	const handle = await qgis.sites.watch(
		{ layer_id: "sites" },
		{
			onEvent: (event) => events.push(event),
			onTerminal: (terminal) => terminals.push(terminal),
		},
	);
	const open = scripted as ScriptedStream | null;
	if (open === null) {
		throw new Error("the harness did not open the stream");
	}
	// `state` is not declared by `sites.watch`; a declared kind with a wrong
	// payload is refused the same way.
	open.emit("state", { anything: 1 });
	await harness.settled();
	expect(events).toEqual([]);
	expect(terminals).toHaveLength(1);
	expect(terminals[0]?.kind).toBe("error");
	expect(terminals[0]?.message).toContain("sites.watch: the event");
	expect(handle.closed).toBe(true);
	expect(harness.openSubscriptions).toEqual([]);
	qgis.close();
});

test("a stream request is checked before anything is sent", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	const failure = await qgis.sites.watch({ layer_id: 1 } as never, {}).then(
		() => null,
		(error: unknown) => error,
	);
	expect(failure).toBeInstanceOf(QgisSdkContractError);
	expect(harness.calls.filter((call) => call.kind === "subscribe")).toEqual([]);
	qgis.close();
});

// -- the host surface (AC #5) -------------------------------------------------

test("`host` is the curated surface on the same client, with every grant by default", async () => {
	const harness = createBridgeHarness(schema);
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	expect(qgis.host.granted).toEqual([]);
	await qgis.ready;
	expect(qgis.host.granted).toEqual([...HOST_OPERATIONS]);
	expect(Object.keys(qgis.host).sort()).toEqual([
		"algorithms",
		"files",
		"granted",
		"layers",
		"network",
		"notifications",
		"project",
		"settings",
		"styles",
		"theme",
	]);
	harness.expectInvoke("layers.list", (payload) => {
		expect(payload).toEqual({ limit: 2 });
		return { items: [], truncated: false };
	});
	await expect(qgis.host.layers.list({ limit: 2 })).resolves.toEqual({
		items: [],
		truncated: false,
	});
	harness.assertSatisfied();
	qgis.close();
});

test("a narrowed grant set is what the handshake advertised, and the host refuses the rest", async () => {
	const harness = createBridgeHarness(schema, {
		granted: ["layers.get", "settings.get"],
	});
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	await qgis.ready;
	expect(qgis.host.granted).toEqual(["layers.get", "settings.get"]);
	expect(Object.isFrozen(qgis.host.granted)).toBe(true);
	// The plugin's own operations never appear among the host grants.
	expect(qgis.host.granted).not.toContain("sites.summary");
	harness.expectInvoke("layers.list", () =>
		fault("not_authorized", "This view is not authorized for that operation"),
	);
	const refused = await qgis.host.layers.list({}).then(
		() => null,
		(error: unknown) => error,
	);
	expect(refused).toBeInstanceOf(QgisSdkBridgeRemoteError);
	expect((refused as QgisSdkBridgeRemoteError).failure.code).toBe(
		"not_authorized",
	);
	harness.assertSatisfied();
	qgis.close();
});

test("`ready` rejects when the host refuses the handshake", async () => {
	const harness = createBridgeHarness(schema);
	const refusing: BridgeHarness = {
		...harness,
		send: (message) => {
			const raw = message as { kind?: string; call_id: string };
			if (raw.kind === "handshake") {
				harness.deliver({
					protocol: 1,
					call_id: raw.call_id,
					ok: false,
					error: { code: "stale_generation", message: "gone" },
				});
				return;
			}
			harness.send(message);
		},
		subscribe: (listener) => harness.subscribe(listener),
	};
	const qgis = QgisSdk.fromBridgeSchema(schema, { transport: refusing });
	const failure = await qgis.ready.then(
		() => null,
		(error: unknown) => error,
	);
	expect(failure).toBeInstanceOf(QgisSdkBridgeRemoteError);
	expect(qgis.host.granted).toEqual([]);
	qgis.close();
});

// -- ownership and refusals ---------------------------------------------------

test("close() closes an owned client and leaves a passed-in client alone", () => {
	const harness = createBridgeHarness(schema);
	const owned = QgisSdk.fromBridgeSchema(schema, { transport: harness });
	expect(harness.listeners).toBe(1);
	owned.close();
	expect(owned.client.isClosed).toBe(true);
	expect(harness.listeners).toBe(0);

	const client = new BridgeClient(harness);
	const shared = QgisSdk.fromBridgeSchema(schema, { client });
	expect(shared.client).toBe(client);
	shared.close();
	expect(client.isClosed).toBe(false);
	client.close();
});

test("a client and a transport together are refused", () => {
	const harness = createBridgeHarness(schema);
	const client = new BridgeClient(harness);
	expect(() =>
		QgisSdk.fromBridgeSchema(schema, { client, transport: harness }),
	).toThrow(QgisSdkDeclarationError);
	client.close();
});

test("outside a QGIS web view the default transport refuses synchronously", () => {
	expect(() => QgisSdk.fromBridgeSchema(schema)).toThrow(
		QgisSdkWebChannelError,
	);
});

test("an operation id whose first segment is a core member is refused", () => {
	for (const member of QGIS_SDK_MEMBERS) {
		for (const id of [member, `${member}.list`]) {
			const shadowing = defineBridgeSchema({
				schema_version: 1,
				id: "demo",
				title: "Demo",
				actions: [describeAction(id)],
			});
			expect(() =>
				QgisSdk.fromBridgeSchema(shadowing, {
					transport: createBridgeHarness(),
				}),
			).toThrow(QgisSdkDeclarationError);
		}
	}
});

test("the host's theme is what the handshake carried, and null without one", async () => {
	const theme = {
		palette: { window: "#323232", windowText: "#dddddd" },
		dark: true,
	};
	const themed = createBridgeHarness(schema, { theme });
	const inside = QgisSdk.fromBridgeSchema(schema, { transport: themed });
	expect(inside.host.theme).toBeNull();
	await inside.ready;
	expect(inside.host.theme).toEqual(theme);
	expect(Object.isFrozen(inside.host.theme)).toBe(true);
	expect(Object.isFrozen(inside.host.theme?.palette)).toBe(true);
	inside.close();

	const plain = createBridgeHarness(schema);
	const outside = QgisSdk.fromBridgeSchema(schema, { transport: plain });
	await outside.ready;
	expect(outside.host.theme).toBeNull();
	expect(outside.host.granted).toEqual([...HOST_OPERATIONS]);
	outside.close();
});

function handshakeAnswering(value: Record<string, unknown>): BridgeHarness {
	const harness = createBridgeHarness(schema);
	return {
		...harness,
		send: (message) => {
			const raw = message as { kind?: string; call_id: string };
			if (raw.kind === "handshake") {
				harness.deliver({ protocol: 1, call_id: raw.call_id, ok: true, value });
				return;
			}
			harness.send(message);
		},
		subscribe: (listener) => harness.subscribe(listener),
	};
}

test("a malformed theme is ignored rather than refused, and non-string colours dropped", async () => {
	const partial = QgisSdk.fromBridgeSchema(schema, {
		transport: handshakeAnswering({
			operations: [],
			theme: { palette: { window: "#ffffff", mid: 7 } },
		}),
	});
	await partial.ready;
	expect(partial.host.theme).toEqual({
		palette: { window: "#ffffff" },
		dark: false,
	});
	partial.close();

	const loose = QgisSdk.fromBridgeSchema(schema, {
		transport: handshakeAnswering({ operations: [], theme: "dark" }),
	});
	await loose.ready;
	expect(loose.host.theme).toBeNull();
	loose.close();
});
