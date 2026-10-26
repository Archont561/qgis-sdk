/**
 * The one behaviour suite every binding must pass (TASK-69 AC #1).
 *
 * The stores own the behaviour; an adapter only subscribes. So the suite is
 * written once against a `Driver` - "bind this operation, give me its
 * snapshots and controls" - and `tests/stores.test.ts`, `tests/react-stores
 * .test.ts`, `tests/vue.test.ts` and `tests/svelte.test.ts` each run it
 * through their own driver. A behaviour that holds for the core and fails
 * for one adapter is an adapter bug; one that fails everywhere is a core bug.
 * Either way the failure names the binding.
 */

import { describe, expect, test } from "bun:test";
import type { VectorLayerInfo } from "../src/generated/host";
import { QgisSdk } from "../src/qgis-sdk";
import { type BridgeSchema, defineBridgeSchema } from "../src/schema";
import type {
	FormField,
	FormOptions,
	FormState,
	HostQueryState,
	Operation,
	OperationState,
	Stream,
	StreamHandlersLike,
	StreamState,
} from "../src/stores";
import {
	createBridgeHarness,
	fault,
	type ScriptedStream,
} from "../src/testing";
import schema, {
	type Operations,
	type SitesWatchEvent,
	type Streams,
} from "./contracts/generated/clients/sites.schema";

/** A binding as the suite sees it: snapshots in order, plus its controls. */
export interface Bound<T> {
	/** The latest snapshot. */
	current(): T;
	/** Every distinct snapshot since binding, in order. */
	readonly history: readonly T[];
	/** Unmount, dispose, or end the scope: what the framework does on teardown. */
	dispose(): Promise<void>;
}

export interface BoundOperation<I, R> extends Bound<OperationState<R>> {
	run(input: I): Promise<R | undefined>;
	abort(): void;
	reset(): void;
}

export interface BoundStream<I, E> extends Bound<StreamState<E>> {
	/** Change the input the binding follows; `null` closes. */
	setInput(input: I | null): Promise<void>;
	/** Replace the handlers the next frames reach. */
	setHandlers(handlers: StreamHandlersLike<E>): Promise<void>;
}

export interface BoundForm<R> extends Bound<FormState<R>> {
	readonly fields: readonly FormField[];
	set(name: string, value: unknown): Promise<void>;
	submit(): Promise<R | undefined>;
	reset(): Promise<void>;
}

export interface BoundQuery<T> extends Bound<HostQueryState<T>> {
	refresh(): Promise<T | undefined>;
}

/** How one binding builds the four bindings and lets asynchrony settle. */
export interface Driver {
	operation<I, R>(operation: Operation<I, R>): Promise<BoundOperation<I, R>>;
	stream<I, E>(
		open: Stream<I, E>,
		input: I | null,
		handlers?: StreamHandlersLike<E>,
	): Promise<BoundStream<I, E>>;
	form<R>(
		qgis: QgisSdk<FormOperations, Record<never, never>>,
		id: "buffer",
		options?: FormOptions,
	): Promise<BoundForm<R>>;
	layers(
		qgis: QgisSdk<FormOperations, Record<never, never>>,
	): Promise<BoundQuery<readonly VectorLayerInfo[]>>;
	/** Let every queued reply, frame and re-render land. */
	settle(): Promise<void>;
}

// -- the form schema: one action with the kinds a picker needs ----------------

export interface BufferRequest {
	readonly layer_id: string;
	readonly distance_metres: number;
	readonly note?: string | null;
	readonly mode?: "fast" | "exact";
}

export interface FormOperations {
	readonly buffer: {
		readonly request: BufferRequest;
		readonly result: { readonly id: string };
	};
}

export const formSchema: BridgeSchema<
	FormOperations,
	Record<never, never>
> = defineBridgeSchema<FormOperations, Record<never, never>>({
	schema_version: 1,
	id: "org.example.forms",
	title: "Forms",
	actions: [
		{
			id: "buffer",
			title: "Buffer",
			handler: "buffer",
			request: {
				type: "object",
				properties: {
					layer_id: { type: "string", "x-qgis-sdk": { kind: "layer" } },
					distance_metres: {
						type: "number",
						minimum: 0,
						"x-qgis-sdk": { kind: "metres" },
					},
					note: { anyOf: [{ type: "string" }, { type: "null" }] },
					mode: { enum: ["fast", "exact"] },
				},
				additionalProperties: false,
				required: ["layer_id", "distance_metres"],
			},
			result: {
				type: "object",
				properties: { id: { type: "string" } },
				required: ["id"],
				additionalProperties: false,
			},
		},
	],
	streams: [],
});

type SitesOp = "sites.summary" | "sites.watch";

const layer = (id: string): VectorLayerInfo => ({
	id,
	name: id.toUpperCase(),
	geometry_type: "point",
	crs: "EPSG:4326",
	field_names: ["fid", "name"],
});

/** A promise the test releases by hand, so `pending` is observable. */
export function gate(): { readonly promise: Promise<void>; release(): void } {
	let release: () => void = () => undefined;
	const promise = new Promise<void>((resolve) => {
		release = resolve;
	});
	return { promise, release: () => release() };
}

function statuses<T extends { readonly status: string }>(
	history: readonly T[],
): string[] {
	return history.map((state) => state.status);
}

/** Register the suite for one driver. */
export function describeStoreBehaviour(name: string, driver: Driver): void {
	describe(`${name}: OperationStore`, () => {
		test("moves idle -> pending -> ok, and a fault is an error with its code", async () => {
			const harness = createBridgeHarness<SitesOp>();
			const releases: (() => void)[] = [];
			const gated = <T>(reply: T): Promise<T> =>
				new Promise<T>((resolve) => {
					releases.push(() => resolve(reply));
				});
			harness.expectInvoke("sites.summary", () =>
				gated({ total: 1, largest: "a", mode: "fast" }),
			);
			harness.expectInvoke("sites.summary", () =>
				gated(fault("forbidden", "nope")),
			);
			const qgis = QgisSdk.fromBridgeSchema<Operations, Streams>(schema, {
				transport: harness,
			});
			const bound = await driver.operation(qgis.sites.summary);
			expect(bound.current()).toEqual({ status: "idle" });

			const first = bound.run({ layer_id: "a" });
			await driver.settle();
			expect(bound.current().status).toBe("pending");
			releases.shift()?.();
			await expect(first).resolves.toEqual({
				total: 1,
				largest: "a",
				mode: "fast",
			});
			await driver.settle();
			expect(bound.current()).toEqual({
				status: "ok",
				value: { total: 1, largest: "a", mode: "fast" },
			});

			const second = bound.run({ layer_id: "b" });
			await driver.settle();
			releases.shift()?.();
			await expect(second).resolves.toBeUndefined();
			await driver.settle();

			expect(statuses(bound.history)).toEqual([
				"idle",
				"pending",
				"ok",
				"pending",
				"error",
			]);
			const last = bound.current();
			expect(last.status === "error" && last.error).toMatchObject({
				code: "forbidden",
			});
			harness.assertSatisfied();
			await bound.dispose();
			qgis.close();
		});

		test("the latest run wins, a stale reply is ignored, and reset returns to idle", async () => {
			const harness = createBridgeHarness<SitesOp>();
			const firstReply = gate();
			harness.expectInvoke("sites.summary", async () => {
				await firstReply.promise;
				return { total: 1, largest: "first", mode: "fast" };
			});
			harness.expectInvoke("sites.summary", () => ({
				total: 2,
				largest: "second",
				mode: "fast",
			}));
			const qgis = QgisSdk.fromBridgeSchema<Operations, Streams>(schema, {
				transport: harness,
			});
			const bound = await driver.operation(qgis.sites.summary);

			const first = bound.run({ layer_id: "first" });
			await driver.settle();
			await expect(bound.run({ layer_id: "second" })).resolves.toMatchObject({
				largest: "second",
			});
			await driver.settle();
			const afterSecond = bound.current();
			expect(afterSecond.status === "ok" && afterSecond.value.largest).toBe(
				"second",
			);
			firstReply.release();
			await expect(first).resolves.toBeUndefined();
			await driver.settle();
			expect(bound.current()).toBe(afterSecond);

			bound.reset();
			await driver.settle();
			expect(bound.current()).toEqual({ status: "idle" });
			harness.assertSatisfied();
			await bound.dispose();
			qgis.close();
		});

		test("disposing while a call is pending aborts it locally and settles nothing afterwards", async () => {
			const harness = createBridgeHarness<SitesOp>();
			const reply = gate();
			harness.expectInvoke("sites.summary", async () => {
				await reply.promise;
				return { total: 1, largest: "late", mode: "fast" };
			});
			const qgis = QgisSdk.fromBridgeSchema<Operations, Streams>(schema, {
				transport: harness,
			});
			const bound = await driver.operation(qgis.sites.summary);
			const pending = bound.run({ layer_id: "a" });
			await driver.settle();
			const seen = bound.history.length;

			await bound.dispose();
			await expect(pending).resolves.toBeUndefined();
			reply.release();
			await driver.settle();

			expect(bound.history.length).toBe(seen);
			expect(bound.current().status).toBe("pending");
			harness.assertSatisfied();
			qgis.close();
		});
	});

	describe(`${name}: StreamStore`, () => {
		test("opens, delivers events to the latest handler, follows input content, and closes on null", async () => {
			const harness = createBridgeHarness<SitesOp>();
			let stream: ScriptedStream | undefined;
			harness.expectSubscribe("sites.watch", (_payload, s) => {
				stream = s;
			});
			const qgis = QgisSdk.fromBridgeSchema<Operations, Streams>(schema, {
				transport: harness,
			});
			const first: SitesWatchEvent[] = [];
			const second: SitesWatchEvent[] = [];
			const bound = await driver.stream(
				qgis.sites.watch,
				{ layer_id: "sites", every_ms: 5 },
				{ onEvent: (event) => first.push(event) },
			);
			await driver.settle();
			expect(harness.openSubscriptions).toHaveLength(1);
			expect(bound.current().status).toBe("open");

			// A new handler identity and an equal input reopen nothing.
			await bound.setHandlers({ onEvent: (event) => second.push(event) });
			await bound.setInput({ every_ms: 5, layer_id: "sites" });
			await driver.settle();
			stream?.emit("data", { change: "added", count: 2, layer_id: "sites" });
			await harness.settled();
			await driver.settle();

			expect(first).toEqual([]);
			expect(second).toEqual([
				{
					kind: "data",
					payload: { change: "added", count: 2, layer_id: "sites" },
				},
			]);
			expect(bound.current().lastEvent).toEqual(second[0] as SitesWatchEvent);
			expect(
				harness.calls.filter((call) => call.kind === "subscribe"),
			).toHaveLength(1);
			// An adapter may bind after the first input was set, so the head of
			// the history is its own; the tail is the store's.
			expect(statuses(bound.history).slice(-3)).toEqual([
				"opening",
				"open",
				"open",
			]);

			// A different input closes the old stream and opens a new one.
			harness.expectSubscribe("sites.watch", () => {});
			await bound.setInput({ layer_id: "other", every_ms: 5 });
			await driver.settle();
			await harness.settled();
			expect(harness.openSubscriptions).toHaveLength(1);
			expect(
				harness.calls.filter((call) => call.kind === "subscribe"),
			).toHaveLength(2);
			expect(bound.current()).toMatchObject({
				status: "open",
				lastEvent: null,
			});

			await bound.setInput(null);
			await driver.settle();
			await harness.settled();
			expect(harness.openSubscriptions).toEqual([]);
			expect(harness.calls.at(-1)?.kind).toBe("unsubscribe");
			expect(bound.current().status).toBe("idle");
			harness.assertSatisfied();
			await bound.dispose();
			qgis.close();
		});

		test("a host terminal ends the stream once, a refusal is a failed state with its code", async () => {
			const harness = createBridgeHarness<SitesOp>();
			harness.expectSubscribe("sites.watch", (_payload, s) => {
				s.emit("data", { change: "added", count: 1, layer_id: "sites" });
				s.end({ kind: "complete" });
			});
			const qgis = QgisSdk.fromBridgeSchema<Operations, Streams>(schema, {
				transport: harness,
			});
			const terminals: string[] = [];
			const bound = await driver.stream(
				qgis.sites.watch,
				{ layer_id: "sites" },
				{ onTerminal: (terminal) => terminals.push(terminal.kind) },
			);
			await driver.settle();
			await harness.settled();
			await driver.settle();
			expect(bound.current()).toMatchObject({
				status: "ended",
				terminal: { kind: "complete" },
			});
			expect(terminals).toEqual(["complete"]);
			expect(harness.openSubscriptions).toEqual([]);

			harness.expectSubscribe("sites.watch", () => fault("forbidden", "no"));
			await bound.setInput({ layer_id: "refused" });
			await driver.settle();
			await harness.settled();
			await driver.settle();
			expect(bound.current().status).toBe("failed");
			expect(bound.current().error).toMatchObject({ code: "forbidden" });
			harness.assertSatisfied();
			await bound.dispose();
			qgis.close();
		});

		test("disposing before the host acknowledges still closes the subscription", async () => {
			const harness = createBridgeHarness<SitesOp>();
			const ack = gate();
			harness.expectSubscribe("sites.watch", () => {}, {
				ack: () => ack.promise,
			});
			const qgis = QgisSdk.fromBridgeSchema<Operations, Streams>(schema, {
				transport: harness,
			});
			const bound = await driver.stream(qgis.sites.watch, {
				layer_id: "sites",
				every_ms: 1,
			});
			await driver.settle();
			await bound.dispose();
			ack.release();
			await harness.settled();
			await driver.settle();

			expect(harness.openSubscriptions).toEqual([]);
			expect(
				harness.calls
					.filter((call) => call.kind !== "handshake")
					.map((call) => call.kind),
			).toEqual(["subscribe", "unsubscribe"]);
			harness.assertSatisfied();
			qgis.close();
		});
	});

	describe(`${name}: FormStore`, () => {
		test("fields come from the declaration, values coerce, and an invalid submit makes no call", async () => {
			const harness = createBridgeHarness(formSchema);
			const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
			const bound = await driver.form<{ id: string }>(qgis, "buffer", {
				initial: { mode: "fast" },
			});

			expect(
				bound.fields.map((field) => [
					field.name,
					field.label,
					field.kind,
					field.required,
					field.nullable,
				]),
			).toEqual([
				["layer_id", "Layer id", "layer", true, false],
				["distance_metres", "Distance metres", "metres", true, false],
				["note", "Note", "text", false, true],
				["mode", "Mode", "choice", false, false],
			]);
			expect(bound.fields[1]?.details).toEqual({ minimum: 0 });
			expect(bound.fields[3]?.choices).toEqual(["fast", "exact"]);
			expect(bound.current()).toMatchObject({
				values: { mode: "fast" },
				valid: false,
				dirty: false,
				submitted: false,
				errors: { layer_id: "required", distance_metres: "required" },
				submission: { status: "idle" },
			});

			await expect(bound.submit()).resolves.toBeUndefined();
			await driver.settle();
			expect(bound.current()).toMatchObject({ submitted: true, valid: false });
			expect(harness.calls.filter((call) => call.kind === "invoke")).toEqual(
				[],
			);

			await bound.set("layer_id", "roads");
			await bound.set("distance_metres", "12.5");
			await driver.settle();
			expect(bound.current()).toMatchObject({
				values: { layer_id: "roads", distance_metres: 12.5, mode: "fast" },
				valid: true,
				dirty: true,
				errors: {},
			});

			await bound.set("distance_metres", "-1");
			await driver.settle();
			expect(bound.current().errors).toEqual({ distance_metres: "minimum" });
			await bound.set("distance_metres", "");
			await driver.settle();
			expect(bound.current().errors).toEqual({ distance_metres: "required" });

			harness.assertSatisfied();
			await bound.dispose();
			qgis.close();
		});

		test("a valid submit runs the action and the submission follows it; reset returns to the start", async () => {
			const harness = createBridgeHarness(formSchema);
			harness.expectInvoke("buffer", (payload) => ({
				id: `${payload.layer_id}:${payload.distance_metres}`,
			}));
			harness.expectInvoke("buffer", () => fault("forbidden", "no"));
			const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
			const bound = await driver.form<{ id: string }>(qgis, "buffer", {
				initial: { mode: "fast" },
			});

			await bound.set("layer_id", "roads");
			await bound.set("distance_metres", 3);
			await expect(bound.submit()).resolves.toEqual({ id: "roads:3" });
			await driver.settle();
			expect(bound.current()).toMatchObject({
				submitted: true,
				submission: { status: "ok", value: { id: "roads:3" } },
			});
			expect(
				statuses(bound.history.map((state) => state.submission)),
			).toContain("pending");

			await expect(bound.submit()).resolves.toBeUndefined();
			await driver.settle();
			const refused = bound.current().submission;
			expect(refused.status === "error" && refused.error).toMatchObject({
				code: "forbidden",
			});

			await bound.reset();
			await driver.settle();
			expect(bound.current()).toMatchObject({
				values: { mode: "fast" },
				dirty: false,
				submitted: false,
				submission: { status: "idle" },
			});
			harness.assertSatisfied();
			await bound.dispose();
			qgis.close();
		});
	});

	describe(`${name}: HostQueryStore`, () => {
		test("refuses before any call when the handshake did not grant the operation", async () => {
			const harness = createBridgeHarness(formSchema, { granted: [] });
			const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
			const bound = await driver.layers(qgis);
			expect(bound.current()).toEqual({ status: "idle" });

			await expect(bound.refresh()).resolves.toBeUndefined();
			await driver.settle();
			expect(bound.current()).toEqual({
				status: "refused",
				operation: "layers.list",
				message: "this view was not granted layers.list",
			});
			expect(statuses(bound.history)).toEqual(["idle", "loading", "refused"]);
			expect(harness.calls.map((call) => call.kind)).toEqual(["handshake"]);
			harness.assertSatisfied();
			await bound.dispose();
			qgis.close();
		});

		test("follows every page when granted, and a fault is an error", async () => {
			const harness = createBridgeHarness(formSchema, {
				granted: ["layers.list"],
			});
			harness.expectInvoke("layers.list", () => ({
				items: [layer("a"), layer("b")],
				next_cursor: "2",
				truncated: true,
			}));
			harness.expectInvoke<{ cursor?: string }>("layers.list", (payload) => {
				expect(payload.cursor).toBe("2");
				return { items: [layer("c")], truncated: false };
			});
			harness.expectInvoke("layers.list", () => fault("internal", "boom"));
			const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
			const bound = await driver.layers(qgis);

			const all = await bound.refresh();
			await driver.settle();
			expect(bound.current()).not.toMatchObject({ status: "error" });
			expect(all?.map((item) => item.id)).toEqual(["a", "b", "c"]);
			expect(bound.current()).toMatchObject({ status: "ok" });

			await expect(bound.refresh()).resolves.toBeUndefined();
			await driver.settle();
			const failed = bound.current();
			expect(failed.status === "error" && failed.error).toMatchObject({
				code: "internal",
			});
			expect(statuses(bound.history)).toEqual([
				"idle",
				"loading",
				"ok",
				"loading",
				"error",
			]);
			harness.assertSatisfied();
			await bound.dispose();
			qgis.close();
		});
	});
}
