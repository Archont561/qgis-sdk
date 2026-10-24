import { expect, test } from "@archont561/bun-test-utils";
import { BRIDGE_PROTOCOL_VERSION, BridgeClient } from "../src/bridge";
import {
	type BridgeClientLike,
	CONTRACT_FINGERPRINT,
	ContractError,
	createOperations,
	type InvokeOptions,
	SitesWatchEvent as isSitesWatchEvent,
	OPERATIONS,
	PLUGIN_DESCRIPTION_SCHEMA_VERSION,
	PLUGIN_ID,
	SitesDetailsRequest,
	SitesDetailsResult,
	SitesSummaryRequest,
	type SitesWatchEvent,
	type StreamHandle,
	type StreamTerminal,
} from "./contracts/generated/clients/sites";

type Sent = {
	readonly operation: string;
	readonly payload: Readonly<Record<string, unknown>> | undefined;
	readonly options: InvokeOptions | undefined;
};

type LooseEvent = { readonly kind: string; readonly payload: unknown };

type Scripted = {
	readonly client: BridgeClientLike;
	readonly sent: Sent[];
	/** Push one already-parsed event into the open subscription. */
	readonly emit: (event: LooseEvent) => void;
	/** End the open subscription the way the kernel would. */
	readonly end: (terminal: StreamTerminal) => void;
	readonly closed: () => number;
};

/**
 * A client that records what the generated module asked for and lets a test
 * play the kernel: it hands back parsed events and terminals, never frames.
 */
function scripted(reply: unknown): Scripted {
	const sent: Sent[] = [];
	let handlers: Parameters<BridgeClientLike["subscribe"]>[2];
	let closed = 0;
	return {
		sent,
		closed: () => closed,
		emit: (event) => {
			handlers?.onEvent?.(event as never);
		},
		end: (terminal) => {
			handlers?.onTerminal?.(terminal);
		},
		client: {
			invoke: (
				operation: string,
				payload?: Readonly<Record<string, unknown>>,
				options?: InvokeOptions,
			) => {
				sent.push({ operation, payload, options });
				return Promise.resolve(reply);
			},
			subscribe: (operation, payload, given, options) => {
				sent.push({ operation, payload, options });
				handlers = given;
				const handle: StreamHandle = {
					id: "s1",
					get closed() {
						return closed > 0;
					},
					close: () => {
						closed += 1;
						given?.onTerminal?.({ kind: "disposed" });
					},
				};
				return Promise.resolve(handle);
			},
		},
	};
}

const summary = { total: 2, largest: "sites", mode: "fast" };

test("the generated module names the plugin and its description version", () => {
	expect(PLUGIN_ID).toBe("org.example.sites");
	expect(PLUGIN_DESCRIPTION_SCHEMA_VERSION).toBe(1);
	expect(CONTRACT_FINGERPRINT.startsWith("sha256:")).toBe(true);
	expect(CONTRACT_FINGERPRINT.length).toBe("sha256:".length + 64);
});

test("the module lists every declared operation id, streams included", () => {
	expect(OPERATIONS).toEqual([
		"sites.details",
		"sites.refresh",
		"sites.summary",
		"sites.watch",
	]);
});

test("the public surface is the generated map, not a generic invoke", () => {
	const operations = createOperations(scripted(summary).client);
	expect(Object.keys(operations)).toEqual(["sites"]);
	expect("invoke" in operations).toBe(false);
	expect("subscribe" in operations).toBe(false);
});

test("an input validator is strict about unknown arguments", () => {
	expect(SitesSummaryRequest({ layer_id: "sites" }, true)).toBe(true);
	expect(SitesSummaryRequest({ layer_id: "sites", extra: 1 }, true)).toBe(
		false,
	);
	// The same payload is tolerated when the flag is off, which is how a result
	// validator behaves: additive for responses, closed for arguments.
	expect(SitesSummaryRequest({ layer_id: "sites", extra: 1 })).toBe(true);
});

test("strictness reaches nested input objects", () => {
	const accepted = { layer_id: "sites", options: { limit: 1 } };
	expect(SitesDetailsRequest(accepted, true)).toBe(true);
	expect(
		SitesDetailsRequest({ layer_id: "sites", options: { bogus: 1 } }, true),
	).toBe(false);
});

test("an input validator rejects a wrong type and an unknown enum branch", () => {
	expect(SitesSummaryRequest({ layer_id: 1 }, true)).toBe(false);
	expect(SitesSummaryRequest({ layer_id: "sites", limit: 1.5 }, true)).toBe(
		false,
	);
	expect(SitesSummaryRequest({ layer_id: "sites", mode: "slow" }, true)).toBe(
		false,
	);
});

test("a result validator tolerates a field the host added later", () => {
	const extended = {
		layer_id: "sites",
		field_names: ["a"],
		options: { include_fields: true, limit: 1, future: "ok" },
		added_by_a_newer_host: 1,
	};
	expect(SitesDetailsResult(extended)).toBe(true);
	// Still closed in the one direction that would hide a broken host.
	expect(SitesDetailsResult(extended, true)).toBe(false);
	const { options: _omitted, ...missing } = extended;
	expect(SitesDetailsResult(missing)).toBe(false);
});

test("createOperations sends the declared operation and returns the result", async () => {
	const { client, sent } = scripted(summary);
	const operations = createOperations(client);
	const options: InvokeOptions = {};
	const result = await operations.sites.summary({ layer_id: "sites" }, options);
	expect(result.total).toBe(2);
	expect(sent.length).toBe(1);
	expect(sent[0]?.operation).toBe("sites.summary");
	expect(sent[0]?.payload).toEqual({ layer_id: "sites" });
	expect(sent[0]?.options).toBe(options);
});

test("an action with no declared inputs still invokes with an empty payload", async () => {
	const { client, sent } = scripted(summary);
	await createOperations(client).sites.refresh();
	expect(sent[0]?.operation).toBe("sites.refresh");
	expect(sent[0]?.payload).toEqual({});
});

test("a malformed argument throws before the transport is touched", async () => {
	const { client, sent } = scripted(summary);
	const failing = createOperations(client).sites.summary({
		layer_id: "sites",
		guess: true,
	} as never);
	await expect(failing).rejects.toThrow(ContractError);
	expect(sent.length).toBe(0);
});

test("a malformed response throws instead of leaking a wrong type", async () => {
	const { client } = scripted({
		total: "many",
		largest: "sites",
		mode: "fast",
	});
	const failing = createOperations(client).sites.summary({ layer_id: "sites" });
	await expect(failing).rejects.toThrow(ContractError);
});

test("the error names the operation it failed on", async () => {
	const { client } = scripted({ total: 1 });
	try {
		await createOperations(client).sites.refresh();
	} catch (error) {
		expect(error instanceof ContractError).toBe(true);
		expect((error as ContractError).message).toContain("sites.refresh");
		return;
	}
	throw new Error("expected the result validator to reject the reply");
});

// -- streams (decision-28) -----------------------------------------------------

const change = { layer_id: "roads", change: "added", count: 2 } as const;

test("the event predicate narrows by kind and validates the payload of that kind", () => {
	expect(isSitesWatchEvent({ kind: "data", payload: change })).toBe(true);
	expect(
		isSitesWatchEvent({ kind: "progress", payload: { done: 1, total: 2 } }),
	).toBe(true);
	// A kind the stream did not declare is refused even though the kernel knows it.
	expect(isSitesWatchEvent({ kind: "state", payload: change })).toBe(false);
	// The payload is held to the schema of its own kind, not of any kind.
	expect(isSitesWatchEvent({ kind: "progress", payload: change })).toBe(false);
	expect(
		isSitesWatchEvent({ kind: "data", payload: { ...change, count: "2" } }),
	).toBe(false);
	// Additive, like a result: a field a newer host added is tolerated.
	expect(
		isSitesWatchEvent({ kind: "data", payload: { ...change, extra: 1 } }),
	).toBe(true);
	expect(isSitesWatchEvent(null)).toBe(false);
});

test("a stream member subscribes with the declared operation and delivers typed events", async () => {
	const scripted_ = scripted(summary);
	const events: SitesWatchEvent[] = [];
	const ends: StreamTerminal[] = [];
	const options: InvokeOptions = {};

	const handle = await createOperations(scripted_.client).sites.watch(
		{ layer_id: "roads" },
		{
			onEvent: (event) => {
				events.push(event);
			},
			onTerminal: (terminal) => {
				ends.push(terminal);
			},
		},
		options,
	);

	expect(scripted_.sent).toEqual([
		{ operation: "sites.watch", payload: { layer_id: "roads" }, options },
	]);
	scripted_.emit({ kind: "progress", payload: { done: 0, total: 1 } });
	scripted_.emit({ kind: "data", payload: change });
	scripted_.end({ kind: "complete" });

	expect(events).toEqual([
		{ kind: "progress", payload: { done: 0, total: 1 } },
		{ kind: "data", payload: change },
	]);
	expect(ends).toEqual([{ kind: "complete" }]);
	expect(handle.id).toBe("s1");
	expect(handle.closed).toBe(false);
});

test("a malformed stream request throws before the transport is touched", async () => {
	const scripted_ = scripted(summary);
	const failing = createOperations(scripted_.client).sites.watch(
		{ layer_id: "roads", guess: true } as never,
		{},
	);
	await expect(failing).rejects.toThrow(ContractError);
	expect(scripted_.sent.length).toBe(0);
});

test("an event outside the declaration ends the typed stream once, as an error", async () => {
	const scripted_ = scripted(summary);
	const events: SitesWatchEvent[] = [];
	const ends: StreamTerminal[] = [];

	const handle = await createOperations(scripted_.client).sites.watch(
		{ layer_id: "roads" },
		{
			onEvent: (event) => {
				events.push(event);
			},
			onTerminal: (terminal) => {
				ends.push(terminal);
			},
		},
	);
	scripted_.emit({ kind: "data", payload: change });
	scripted_.emit({ kind: "state", payload: { anything: true } });
	// Whatever the kernel delivers after the violation is not forwarded.
	scripted_.emit({ kind: "data", payload: change });
	scripted_.end({ kind: "complete" });

	expect(events).toEqual([{ kind: "data", payload: change }]);
	expect(ends.length).toBe(1);
	expect(ends[0]?.kind).toBe("error");
	expect(ends[0]?.message).toContain("sites.watch");
	expect(ends[0]?.message).toContain("declared events");
	// The subscription under it was closed exactly once; its `disposed` was
	// swallowed because the typed stream had already ended.
	expect(scripted_.closed()).toBe(1);
	expect(handle.closed).toBe(true);
});

test("closing the handle ends the typed stream as disposed, once", async () => {
	const scripted_ = scripted(summary);
	const ends: StreamTerminal[] = [];
	const handle = await createOperations(scripted_.client).sites.watch(
		{ layer_id: "roads" },
		{ onTerminal: (terminal) => ends.push(terminal) },
	);
	handle.close();
	scripted_.end({ kind: "complete" });
	expect(ends).toEqual([{ kind: "disposed" }]);
});

test("the real BridgeClient satisfies the generated client contract end to end", async () => {
	const listeners = new Set<(message: unknown) => void>();
	const sent: Record<string, unknown>[] = [];
	const client = new BridgeClient({
		send(message) {
			sent.push(message as Record<string, unknown>);
		},
		subscribe(listener) {
			listeners.add(listener);
			return () => listeners.delete(listener);
		},
	});
	const deliver = (message: unknown): void => {
		for (const listener of [...listeners]) listener(message);
	};
	const events: SitesWatchEvent[] = [];
	const ends: StreamTerminal[] = [];

	const pending = createOperations(client).sites.watch(
		{ layer_id: "roads", every_ms: 10 },
		{
			onEvent: (event) => events.push(event),
			onTerminal: (terminal) => ends.push(terminal),
		},
	);
	expect(sent[0]?.kind).toBe("subscribe");
	expect(sent[0]?.operation).toBe("sites.watch");
	expect(sent[0]?.payload).toEqual({ layer_id: "roads", every_ms: 10 });
	deliver({
		protocol: BRIDGE_PROTOCOL_VERSION,
		call_id: sent[0]?.call_id,
		ok: true,
		value: { subscription_id: "s7", capacity: 64 },
	});
	const handle = await pending;
	expect(handle.id).toBe("s7");

	const frame = (seq: number, body: Record<string, unknown>) => ({
		protocol: BRIDGE_PROTOCOL_VERSION,
		subscription_id: "s7",
		seq,
		...body,
	});
	deliver(
		frame(0, { event: { kind: "progress", payload: { done: 0, total: 1 } } }),
	);
	deliver(frame(1, { event: { kind: "data", payload: change } }));
	// The kernel still owns the envelope: a skipped seq is a gap, not an event.
	deliver(frame(3, { event: { kind: "data", payload: change } }));

	expect(events.map((event) => event.kind)).toEqual(["progress", "data"]);
	expect(ends.length).toBe(1);
	expect(ends[0]?.kind).toBe("gap");
	expect(client.activeSubscriptions).toEqual([]);
	expect(sent.some((message) => message.kind === "unsubscribe")).toBe(true);
	client.close();
});
