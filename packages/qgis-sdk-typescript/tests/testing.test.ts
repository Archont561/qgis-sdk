/**
 * The injected per-client harness (TASK-18 AC #3).
 *
 * Everything here is mock evidence: it proves what a page does with the frames
 * a host could send, never what a QWebChannel or a QGIS host does. The native
 * side is qualified by the Python suite and the harnesses recorded in doc-14.
 */

import { expect, test } from "@archont561/bun-test-utils";
import {
	BridgeClient,
	QgisSdkBridgeRemoteError,
	QgisSdkBridgeTimeoutError,
} from "../src/bridge";
import { HOST_OPERATIONS, HOST_SCHEMA_VERSION } from "../src/generated/host";
import {
	createBridgeHarness,
	fault,
	QgisSdkBridgeHarnessError,
	type ScriptedStream,
	SILENCE,
} from "../src/testing";
import {
	createOperations,
	type SitesSummaryRequest,
	type SitesSummaryResult,
	type SitesWatchEvent,
	type SitesWatchRequest,
} from "./contracts/generated/clients/sites";
import schema from "./contracts/generated/clients/sites.schema";

type Op = "sites.summary" | "sites.watch" | "sites.refresh";

test("a scripted reply reaches the typed client, and the call is recorded", async () => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke<SitesSummaryRequest, SitesSummaryResult>(
		"sites.summary",
		(payload) => ({ total: 3, largest: payload.layer_id, mode: "fast" }),
	);
	const operations = createOperations(new BridgeClient(harness));

	const summary = await operations.sites.summary({ layer_id: "sites" });

	expect(summary).toEqual({ total: 3, largest: "sites", mode: "fast" });
	expect(harness.calls).toEqual([
		{
			callId: "c1",
			kind: "invoke",
			operation: "sites.summary",
			payload: { layer_id: "sites" },
		},
	]);
	harness.assertSatisfied();
});

test("an unexpected call fails the client deterministically and the harness", async () => {
	const harness = createBridgeHarness<Op>();
	const client = new BridgeClient(harness);

	const outcome = client.invoke("sites.refresh", {});

	await expect(outcome).rejects.toBeInstanceOf(QgisSdkBridgeRemoteError);
	await expect(outcome).rejects.toMatchObject({ code: "unexpected_call" });
	expect(harness.unexpected.map((call) => call.operation)).toEqual([
		"sites.refresh",
	]);
	expect(() => harness.assertSatisfied()).toThrow(QgisSdkBridgeHarnessError);
	expect(() => harness.assertSatisfied()).toThrow(/unexpected.*sites\.refresh/);
});

test("an expectation that was never met is reported, once per expectation", () => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke("sites.summary", () => ({}));
	harness.expectInvoke("sites.refresh", () => ({}));

	expect(() => harness.assertSatisfied()).toThrow(
		/unmet.*sites\.summary.*sites\.refresh/s,
	);
});

test("expectations for one operation are consumed in order", async () => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke("sites.summary", () => ({ n: 1 }));
	harness.expectInvoke("sites.summary", () => ({ n: 2 }));
	const client = new BridgeClient(harness);

	expect(await client.invoke("sites.summary")).toEqual({ n: 1 });
	expect(await client.invoke("sites.summary")).toEqual({ n: 2 });
	harness.assertSatisfied();
});

test("a scripted fault is a remote failure with the scripted code", async () => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke("sites.summary", () =>
		fault("forbidden", "view may not read sites"),
	);
	const client = new BridgeClient(harness);

	const outcome = client.invoke("sites.summary", { layer_id: "sites" });

	await expect(outcome).rejects.toMatchObject({
		code: "forbidden",
		message: "view may not read sites",
	});
	harness.assertSatisfied();
});

test("a silent expectation lets the client's own timeout speak", async () => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke("sites.summary", () => SILENCE);
	const client = new BridgeClient(harness, { timeoutMs: 5 });

	await expect(client.invoke("sites.summary")).rejects.toBeInstanceOf(
		QgisSdkBridgeTimeoutError,
	);
	harness.assertSatisfied();
});

test("an asynchronous reply is awaited before it is delivered", async () => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke("sites.summary", async () => {
		await new Promise((resolve) => setTimeout(resolve, 1));
		return { late: true };
	});
	const client = new BridgeClient(harness);

	expect(await client.invoke("sites.summary")).toEqual({ late: true });
});

test("a handler that throws is a harness error, not a hung call", async () => {
	const harness = createBridgeHarness<Op>();
	harness.expectInvoke("sites.summary", () => {
		throw new Error("scripted bug");
	});
	const client = new BridgeClient(harness);

	await expect(client.invoke("sites.summary")).rejects.toMatchObject({
		code: "harness_error",
	});
	expect(() => harness.assertSatisfied()).toThrow(/scripted bug/);
});

test("a scripted stream delivers typed events in sequence and ends once", async () => {
	const harness = createBridgeHarness<Op>();
	let stream: ScriptedStream | undefined;
	harness.expectSubscribe<SitesWatchRequest>("sites.watch", (payload, s) => {
		expect(payload.layer_id).toBe("sites");
		stream = s;
	});
	const operations = createOperations(new BridgeClient(harness));
	const events: SitesWatchEvent[] = [];
	const ends: string[] = [];

	const handle = await operations.sites.watch(
		{ layer_id: "sites" },
		{
			onEvent: (event) => events.push(event),
			onTerminal: (terminal) => ends.push(terminal.kind),
		},
	);
	expect(harness.openSubscriptions).toEqual([handle.id]);
	stream?.emit("progress", { done: 1, total: 2 });
	stream?.emit("data", { change: "added", count: 1, layer_id: "sites" });
	stream?.end({ kind: "complete" });
	await harness.settled();

	expect(events).toEqual([
		{ kind: "progress", payload: { done: 1, total: 2 } },
		{
			kind: "data",
			payload: { change: "added", count: 1, layer_id: "sites" },
		},
	]);
	expect(ends).toEqual(["complete"]);
	expect(handle.closed).toBe(true);
	expect(harness.openSubscriptions).toEqual([]);
	harness.assertSatisfied();
});

test("a scripted gap ends the subscription the way the kernel promises", async () => {
	const harness = createBridgeHarness<Op>();
	let stream: ScriptedStream | undefined;
	harness.expectSubscribe("sites.watch", (_payload, s) => {
		stream = s;
	});
	const client = new BridgeClient(harness);
	const ends: unknown[] = [];

	await client.subscribe(
		"sites.watch",
		{ layer_id: "sites" },
		{ onTerminal: (terminal) => ends.push(terminal) },
	);
	stream?.skip(2);
	stream?.emit("data", {});
	await harness.settled();

	expect(ends).toEqual([
		{ kind: "gap", message: "Expected frame 0 but received 2", dropped: 2 },
	]);
	expect(client.sequenceBreaks).toBe(1);
	// The kernel told the host; the harness heard it and no longer counts the
	// stream as open, so this is not a leak.
	expect(harness.calls.map((call) => call.kind)).toEqual([
		"subscribe",
		"unsubscribe",
	]);
	expect(harness.openSubscriptions).toEqual([]);
	harness.assertSatisfied();
});

test("closing from the page reaches the harness and emitting afterwards is a script bug", async () => {
	const harness = createBridgeHarness<Op>();
	let stream: ScriptedStream | undefined;
	harness.expectSubscribe("sites.watch", (_payload, s) => {
		stream = s;
	});
	const client = new BridgeClient(harness);

	const handle = await client.subscribe("sites.watch", { layer_id: "sites" });
	handle.close();
	await harness.settled();

	expect(stream?.open).toBe(false);
	expect(harness.calls.at(-1)).toMatchObject({
		kind: "unsubscribe",
		operation: "sites.watch",
		subscriptionId: handle.id,
	});
	expect(() => stream?.emit("data", {})).toThrow(QgisSdkBridgeHarnessError);
	harness.assertSatisfied();
});

test("a subscription the page never closed is a leak the harness reports", async () => {
	const harness = createBridgeHarness<Op>();
	harness.expectSubscribe("sites.watch", () => {});
	const client = new BridgeClient(harness);

	await client.subscribe("sites.watch", { layer_id: "sites" });

	expect(() => harness.assertSatisfied()).toThrow(/open subscription.*s1/);
	// Closing the client detaches the view; the host disposes what it held
	// for that view, so nothing is leaked once the client is gone.
	client.close();
	expect(harness.openSubscriptions).toEqual([]);
	harness.assertSatisfied();
});

test("a subscription can be refused or left unacknowledged like a call", async () => {
	const harness = createBridgeHarness<Op>();
	harness.expectSubscribe("sites.watch", () => fault("forbidden", "no"));
	harness.expectSubscribe("sites.watch", () => SILENCE);
	const client = new BridgeClient(harness, { timeoutMs: 5 });

	await expect(client.subscribe("sites.watch")).rejects.toMatchObject({
		code: "forbidden",
	});
	await expect(client.subscribe("sites.watch")).rejects.toBeInstanceOf(
		QgisSdkBridgeTimeoutError,
	);
	expect(harness.openSubscriptions).toEqual([]);
	harness.assertSatisfied();
});

test("a raw message can be pushed to script what no expectation covers", async () => {
	const harness = createBridgeHarness<Op>();
	const client = new BridgeClient(harness);

	harness.deliver({ protocol: 1, call_id: "ghost", ok: true, value: null });
	harness.deliver("not even an object");
	await harness.settled();

	expect(client.unmatchedReplies).toBe(2);
	harness.assertSatisfied();
});

test("two harnesses are two hosts: nothing crosses between their clients", async () => {
	const left = createBridgeHarness<Op>();
	const right = createBridgeHarness<Op>();
	left.expectInvoke("sites.summary", () => ({ side: "left" }));
	right.expectInvoke("sites.summary", () => ({ side: "right" }));
	const leftClient = new BridgeClient(left);
	const rightClient = new BridgeClient(right);

	const [a, b] = await Promise.all([
		leftClient.invoke("sites.summary"),
		rightClient.invoke("sites.summary"),
	]);

	expect([a, b]).toEqual([{ side: "left" }, { side: "right" }]);
	expect(left.calls).toHaveLength(1);
	expect(right.calls).toHaveLength(1);
	left.assertSatisfied();
	right.assertSatisfied();
});

test("the harness refuses an envelope that is not the protocol it fakes", () => {
	const harness = createBridgeHarness<Op>();

	expect(() => harness.send({ protocol: 2, call_id: "c1" })).toThrow(
		QgisSdkBridgeHarnessError,
	);
	expect(() =>
		harness.send({ protocol: 1, call_id: "c1", kind: "dance" }),
	).toThrow(QgisSdkBridgeHarnessError);
});

test("the handshake is answered from the schema and the grants, without an expectation", async () => {
	const untyped = createBridgeHarness();
	const bare = new BridgeClient(untyped);
	const plain = (await bare.handshake()) as Record<string, unknown>;
	expect(plain.plugin).toBeNull();
	expect(plain.host_schema_version).toBe(HOST_SCHEMA_VERSION);
	expect(
		(plain.operations as { id: string }[]).map((operation) => operation.id),
	).toEqual([...HOST_OPERATIONS]);
	expect(untyped.calls).toEqual([
		{ callId: "c1", kind: "handshake", operation: "" },
	]);
	untyped.assertSatisfied();
	bare.close();

	const harness = createBridgeHarness(schema, { granted: ["layers.get"] });
	const client = new BridgeClient(harness);
	const reply = (await client.handshake()) as Record<string, unknown>;
	expect(reply.plugin).toBe(schema);
	expect(
		(reply.operations as { id: string }[]).map((operation) => operation.id),
	).toEqual([
		"sites.details",
		"sites.refresh",
		"sites.summary",
		"sites.watch",
		"layers.get",
	]);
	harness.assertSatisfied();
	client.close();
});

test("listeners are counted so a test can see a client detach", () => {
	const harness = createBridgeHarness<Op>();
	const client = new BridgeClient(harness);

	expect(harness.listeners).toBe(1);
	client.close();
	expect(harness.listeners).toBe(0);
});

test("the handshake carries the theme the harness was given, and none by default", async () => {
	const theme = { palette: { window: "#efefef" }, dark: false };
	const themed = createBridgeHarness(schema, { theme });
	const client = new BridgeClient(themed);
	const reply = (await client.handshake()) as Record<string, unknown>;
	expect(reply.theme).toEqual(theme);
	client.close();

	const plain = createBridgeHarness(schema);
	const bare = new BridgeClient(plain);
	const without = (await bare.handshake()) as Record<string, unknown>;
	expect("theme" in without).toBe(false);
	bare.close();
});
