import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@archont561/bun-test-utils";
import {
	BRIDGE_PROTOCOL_VERSION,
	BridgeClient,
	parseInvokeReply,
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
	expect(fixture.cases.length).toBe(9);

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
