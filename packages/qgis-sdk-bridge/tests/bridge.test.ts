import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@archont561/bun-test-utils";
import {
	BRIDGE_PROTOCOL_VERSION,
	BridgeClient,
	parseInvokeReply,
	parseStreamFrame,
	QgisSdkBridgeAbortedError,
	QgisSdkBridgeClosedError,
	QgisSdkBridgeProtocolError,
	QgisSdkBridgeRemoteError,
	QgisSdkBridgeTimeoutError,
	type WireTransport,
} from "@/bridge";

type CaseExpectation = {
	readonly ok: boolean;
	readonly value?: unknown;
	readonly code?: string;
};

type BridgeReply = {
	readonly protocol: number;
	readonly call_id: string;
	readonly ok: boolean;
	readonly value?: unknown;
	readonly error?: { readonly code: string; readonly message: string };
};

type BridgeCase = {
	readonly name: string;
	readonly request: Record<string, unknown>;
	readonly reply: BridgeReply;
	readonly expect: CaseExpectation;
};

const casesPath = fileURLToPath(
	new URL("./contracts/bridge/cases.json", import.meta.url),
);
const fixture = JSON.parse(readFileSync(casesPath, "utf8")) as {
	readonly protocol: number;
	readonly cases: readonly BridgeCase[];
};

type Scripted = {
	readonly transport: WireTransport;
	readonly sent: Record<string, unknown>[];
	readonly deliver: (message: unknown) => void;
	readonly listeners: () => number;
};

function scriptedTransport(): Scripted {
	const sent: Record<string, unknown>[] = [];
	const listeners = new Set<(message: unknown) => void>();
	return {
		transport: {
			send(message: unknown): void {
				sent.push(message as Record<string, unknown>);
			},
			subscribe(listener: (message: unknown) => void): () => void {
				listeners.add(listener);
				return (): void => {
					listeners.delete(listener);
				};
			},
		},
		sent,
		deliver(message: unknown): void {
			for (const listener of [...listeners]) {
				listener(message);
			}
		},
		listeners(): number {
			return listeners.size;
		},
	};
}

function replyFor(
	callId: string,
	body: Record<string, unknown>,
): Record<string, unknown> {
	return { protocol: BRIDGE_PROTOCOL_VERSION, call_id: callId, ...body };
}

test("both languages agree on the checked-in bridge cases", () => {
	expect(fixture.protocol).toBe(BRIDGE_PROTOCOL_VERSION);
	expect(fixture.cases.length).toBe(10);

	for (const item of fixture.cases) {
		const reply = parseInvokeReply(item.reply);
		expect(reply.call_id).toBe(item.reply.call_id);
		expect(reply.ok).toBe(item.expect.ok);
		if (reply.ok) {
			expect(reply.value).toEqual(item.expect.value as unknown);
		} else {
			expect(reply.error.code).toBe(item.expect.code as string);
		}
	}
});

test("parseInvokeReply refuses replies a host could not have produced", () => {
	const refused: unknown[] = [
		null,
		[],
		{ call_id: "c1", ok: true, value: 1 },
		{ protocol: 2, call_id: "c1", ok: true, value: 1 },
		{ protocol: BRIDGE_PROTOCOL_VERSION, call_id: "", ok: true, value: 1 },
		{ protocol: BRIDGE_PROTOCOL_VERSION, call_id: "c1", ok: "yes", value: 1 },
		{ protocol: BRIDGE_PROTOCOL_VERSION, call_id: "c1", ok: true },
		{ protocol: BRIDGE_PROTOCOL_VERSION, call_id: "c1", ok: false },
		{
			protocol: BRIDGE_PROTOCOL_VERSION,
			call_id: "c1",
			ok: false,
			error: { message: "no code" },
		},
		{
			protocol: BRIDGE_PROTOCOL_VERSION,
			call_id: "c1",
			ok: false,
			error: { code: "unknown_operation" },
		},
	];

	for (const raw of refused) {
		expect(() => parseInvokeReply(raw)).toThrow(QgisSdkBridgeProtocolError);
	}
});

test("a call resolves with the value the host produced", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);

	const call = client.invoke("demo.echo", { name: "A" });
	expect(scripted.sent.length).toBe(1);
	const envelope = scripted.sent[0];
	expect(envelope?.protocol).toBe(BRIDGE_PROTOCOL_VERSION);
	expect(envelope?.operation).toBe("demo.echo");
	expect(envelope?.payload).toEqual({ name: "A" });

	scripted.deliver(
		replyFor("c1", { ok: true, value: { echo: { name: "A" } } }),
	);

	expect(await call).toEqual({ echo: { name: "A" } });
	expect(client.pendingCalls).toBe(0);
	client.close();
});

test("a host refusal becomes a typed error carrying the host code", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);

	const call = client.invoke("demo.missing");
	scripted.deliver(
		replyFor("c1", {
			ok: false,
			error: { code: "unknown_operation", message: "no such operation" },
		}),
	);

	await expect(call).rejects.toThrow(QgisSdkBridgeRemoteError);
	await call.catch((error: QgisSdkBridgeRemoteError) => {
		expect(error.code).toBe("unknown_operation");
		expect(error.failure.message).toBe("no such operation");
	});
	client.close();
});

test("a timeout is an unknown outcome and is never retried", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport, { timeoutMs: 5 });

	const call = client.invoke("demo.echo");

	await expect(call).rejects.toThrow(QgisSdkBridgeTimeoutError);
	expect(scripted.sent.length).toBe(1);
	expect(client.pendingCalls).toBe(0);
	client.close();
});

test("an abort is local and distinct from the host cancelling", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);
	const controller = new AbortController();

	const call = client.invoke("demo.echo", {}, { signal: controller.signal });
	controller.abort();

	await expect(call).rejects.toThrow(QgisSdkBridgeAbortedError);
	expect(client.pendingCalls).toBe(0);
	client.close();
});

test("a late or unmatched reply is counted rather than misdelivered", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);

	const call = client.invoke("demo.echo");
	scripted.deliver(replyFor("c1", { ok: true, value: 1 }));
	expect(await call).toBe(1);

	scripted.deliver(replyFor("c1", { ok: true, value: 2 }));
	expect(client.unmatchedReplies).toBe(1);
	client.close();
});

test("a malformed message settles nothing and is remembered", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport, { timeoutMs: 5 });

	const call = client.invoke("demo.echo");
	scripted.deliver({
		protocol: BRIDGE_PROTOCOL_VERSION,
		call_id: "c1",
		ok: "yes",
	});

	expect(client.protocolError).toBeInstanceOf(QgisSdkBridgeProtocolError);
	await expect(call).rejects.toThrow(QgisSdkBridgeTimeoutError);
	client.close();
});

test("closing rejects what is pending and stops listening", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);

	const call = client.invoke("demo.echo");
	client.close();

	await expect(call).rejects.toThrow(QgisSdkBridgeClosedError);
	expect(scripted.listeners()).toBe(0);
	await expect(client.invoke("demo.echo")).rejects.toThrow(
		QgisSdkBridgeClosedError,
	);
});

type FrameCase = {
	readonly name: string;
	readonly frames: readonly unknown[];
};

function streamFixture(): {
	readonly protocol: number;
	readonly streams: readonly FrameCase[];
} {
	return JSON.parse(readFileSync(casesPath, "utf8")) as {
		readonly protocol: number;
		readonly streams: readonly FrameCase[];
	};
}

function ackFor(
	callId: string,
	subscriptionId: string,
): Record<string, unknown> {
	return replyFor(callId, {
		ok: true,
		value: { subscription_id: subscriptionId, capacity: 64 },
	});
}

function frame(subscriptionId: string, seq: number, payload: unknown): unknown {
	return {
		protocol: BRIDGE_PROTOCOL_VERSION,
		subscription_id: subscriptionId,
		seq,
		event: { kind: "data", payload },
	};
}

function ended(subscriptionId: string, seq: number, kind: string): unknown {
	return {
		protocol: BRIDGE_PROTOCOL_VERSION,
		subscription_id: subscriptionId,
		seq,
		terminal: { kind },
	};
}

test("both languages agree on the checked-in stream frames", () => {
	const fixtureStreams = streamFixture();
	expect(fixtureStreams.protocol).toBe(BRIDGE_PROTOCOL_VERSION);
	expect(fixtureStreams.streams.length).toBeGreaterThan(0);

	for (const item of fixtureStreams.streams) {
		const seen = new Map<string, number>();
		for (const raw of item.frames) {
			const parsed = parseStreamFrame(raw);
			const expected = seen.get(parsed.subscription_id) ?? 0;
			expect(parsed.seq).toBe(expected);
			seen.set(parsed.subscription_id, expected + 1);
		}
	}
});

test("parseStreamFrame refuses frames a host could not have produced", () => {
	const refused: unknown[] = [
		null,
		[],
		{ protocol: 1, seq: 0, event: { kind: "data", payload: 1 } },
		{ protocol: 2, subscription_id: "s1", seq: 0, event: { kind: "data" } },
		{ protocol: 1, subscription_id: "s1", seq: -1, event: { kind: "data" } },
		{ protocol: 1, subscription_id: "s1", seq: 0 },
		{
			protocol: 1,
			subscription_id: "s1",
			seq: 0,
			event: { kind: "data", payload: 1 },
			terminal: { kind: "complete" },
		},
		{ protocol: 1, subscription_id: "s1", seq: 0, event: { kind: "nope" } },
		{ protocol: 1, subscription_id: "s1", seq: 0, terminal: { kind: "nope" } },
		{
			protocol: 1,
			subscription_id: "s1",
			seq: 0,
			terminal: { kind: "gap", dropped: -1 },
		},
	];

	for (const raw of refused) {
		expect(() => parseStreamFrame(raw)).toThrow(QgisSdkBridgeProtocolError);
	}
});

test("a subscription delivers events in order and ends once", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);
	const events: unknown[] = [];
	const terminals: string[] = [];

	const pending = client.subscribe(
		"demo.ticks",
		{},
		{
			onEvent: (event) => {
				events.push(event.payload);
			},
			onTerminal: (terminal) => {
				terminals.push(terminal.kind);
			},
		},
	);
	expect(scripted.sent[0]?.kind).toBe("subscribe");
	scripted.deliver(ackFor("c1", "s1"));
	const subscription = await pending;

	expect(subscription.id).toBe("s1");
	expect(client.activeSubscriptions).toEqual(["s1"]);
	scripted.deliver(frame("s1", 0, { index: 0 }));
	scripted.deliver(frame("s1", 1, { index: 1 }));
	scripted.deliver(ended("s1", 2, "complete"));

	expect(events).toEqual([{ index: 0 }, { index: 1 }]);
	expect(terminals).toEqual(["complete"]);
	expect(client.activeSubscriptions).toEqual([]);
	// A terminal frame ends the subscription; the client does not unsubscribe
	// what the host has already ended.
	expect(scripted.sent.filter((m) => m.kind === "unsubscribe")).toEqual([]);
});

test("a frame that skips a sequence ends the subscription instead of delivering", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);
	const terminals: string[] = [];

	const pending = client.subscribe(
		"demo.ticks",
		{},
		{ onTerminal: (terminal) => terminals.push(terminal.kind) },
	);
	scripted.deliver(ackFor("c1", "s1"));
	await pending;

	scripted.deliver(frame("s1", 0, { index: 0 }));
	scripted.deliver(frame("s1", 2, { index: 2 }));

	expect(terminals).toEqual(["gap"]);
	expect(client.sequenceBreaks).toBe(1);
	expect(client.activeSubscriptions).toEqual([]);
	expect(scripted.sent.some((m) => m.kind === "unsubscribe")).toBe(true);
});

test("closing a subscription notifies the host once", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);
	const terminals: string[] = [];

	const pending = client.subscribe(
		"demo.ticks",
		{},
		{ onTerminal: (terminal) => terminals.push(terminal.kind) },
	);
	scripted.deliver(ackFor("c1", "s1"));
	const subscription = await pending;

	subscription.close();
	subscription.close();

	const disposals = scripted.sent.filter((m) => m.kind === "unsubscribe");
	expect(disposals.length).toBe(1);
	expect(disposals[0]?.subscription_id).toBe("s1");
	expect(terminals).toEqual(["disposed"]);
	expect(subscription.closed).toBe(true);

	scripted.deliver(ackFor("c2", "s1"));
	expect(client.unmatchedReplies).toBe(0);
});

test("closing the client ends its subscriptions and ignores later frames", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);
	const terminals: string[] = [];

	const pending = client.subscribe(
		"demo.ticks",
		{},
		{ onTerminal: (terminal) => terminals.push(terminal.kind) },
	);
	scripted.deliver(ackFor("c1", "s1"));
	await pending;

	client.close();
	scripted.deliver(frame("s1", 0, { index: 0 }));

	expect(terminals).toEqual(["disposed"]);
	expect(client.activeSubscriptions).toEqual([]);
	expect(scripted.listeners()).toBe(0);
});

test("frames for a subscription the client does not hold are counted, not routed", async () => {
	const scripted = scriptedTransport();
	const client = new BridgeClient(scripted.transport);

	scripted.deliver(frame("s9", 0, { index: 0 }));
	scripted.deliver({ protocol: 1, subscription_id: "s9", seq: 0 });

	expect(client.activeSubscriptions).toEqual([]);
	expect(client.unmatchedReplies).toBe(2);
	expect(client.protocolError).toBeInstanceOf(QgisSdkBridgeProtocolError);
});
