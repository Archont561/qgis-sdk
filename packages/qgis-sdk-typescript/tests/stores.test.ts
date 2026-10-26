/**
 * The store core, driven directly: what a vanilla page does.
 *
 * The behaviour suite runs here against the stores themselves; the adapter
 * files run the same suite through React, Vue and Svelte. The tests below it
 * cover what only the core exposes: the store contract, the field mapping's
 * refusals, and the typed factories.
 */

import { describe, expect, test } from "bun:test";
import { QgisSdk } from "../src/qgis-sdk";
import {
	type FormFieldKind,
	FormStore,
	formStore,
	HostQueryStore,
	labelFor,
	layerFieldsQuery,
	layersQuery,
	OperationStore,
	QgisSdkStoreError,
	type Store,
	StreamStore,
	schemaFields,
	stableKey,
} from "../src/stores";
import { createBridgeHarness } from "../src/testing";
import {
	type Bound,
	type Driver,
	describeStoreBehaviour,
	formSchema,
	gate,
} from "./store-behaviour";

function record<T>(store: Store<T>): Bound<T> & { stop(): void } {
	const history: T[] = [];
	const stop = store.subscribe((snapshot) => {
		history.push(snapshot);
	});
	return {
		history,
		current: () => store.getSnapshot(),
		stop,
		dispose: async () => {
			stop();
		},
	};
}

const tick = (): Promise<void> =>
	new Promise((resolve) => setTimeout(resolve, 0));

const core: Driver = {
	async operation(operation) {
		const store = new OperationStore(operation);
		const bound = record(store);
		return {
			...bound,
			run: store.run,
			abort: store.abort,
			reset: store.reset,
			dispose: async () => {
				// What an adapter does on teardown: abort, then stop listening.
				store.abort();
				bound.stop();
			},
		};
	},
	async stream(open, input, handlers) {
		const store = new StreamStore(open, handlers);
		const bound = record(store);
		store.setInput(input);
		return {
			...bound,
			setInput: async (next) => {
				store.setInput(next);
			},
			setHandlers: async (next) => {
				store.setHandlers(next);
			},
			dispose: async () => {
				store.close();
				bound.stop();
			},
		};
	},
	async form(qgis, id, options) {
		const store = formStore(qgis, id, options);
		const bound = record(store);
		return {
			...bound,
			fields: store.fields,
			set: async (name: string, value: unknown) => {
				store.set(name, value);
			},
			submit: store.submit,
			reset: async () => {
				store.reset();
			},
			dispose: async () => {
				store.dispose();
				bound.stop();
			},
		} as never;
	},
	async layers(qgis) {
		const store = layersQuery(qgis);
		const bound = record(store);
		return {
			...bound,
			refresh: store.refresh,
			dispose: async () => {
				store.abort();
				bound.stop();
			},
		};
	},
	settle: tick,
};

describeStoreBehaviour("core", core);

describe("the store contract", () => {
	test("subscribe calls the listener at once, then per change, until unsubscribed", async () => {
		const store = new OperationStore(async (value: number) => value * 2);
		const seen: string[] = [];
		const stop = store.subscribe((state) => {
			seen.push(state.status);
		});
		expect(seen).toEqual(["idle"]);
		await store.run(1);
		expect(seen).toEqual(["idle", "pending", "ok"]);
		stop();
		await store.run(2);
		expect(seen).toEqual(["idle", "pending", "ok"]);
	});

	test("getSnapshot is referentially stable between changes", () => {
		const store = new StreamStore(async () => ({
			id: "s",
			closed: false,
			close() {},
		}));
		expect(store.getSnapshot()).toBe(store.getSnapshot());
		store.setInput({ a: 1 });
		const opening = store.getSnapshot();
		store.setInput({ a: 1 });
		expect(store.getSnapshot()).toBe(opening);
	});

	test("an unsubscribe inside a notification does not skip the other listeners", async () => {
		const store = new OperationStore(async () => 1);
		const seen: string[] = [];
		const first = store.subscribe((state) => {
			if (state.status === "pending") {
				first();
			}
			seen.push(`first:${state.status}`);
		});
		store.subscribe((state) => {
			seen.push(`second:${state.status}`);
		});
		await store.run(undefined);
		expect(seen).toEqual([
			"first:idle",
			"second:idle",
			"first:pending",
			"second:pending",
			"second:ok",
		]);
	});

	test("stableKey ignores field order and nothing else", () => {
		expect(stableKey({ a: 1, b: [{ d: 1, c: 2 }] })).toBe(
			stableKey({ b: [{ c: 2, d: 1 }], a: 1 }),
		);
		expect(stableKey({ a: 1 })).not.toBe(stableKey({ a: "1" }));
	});
});

describe("schemaFields", () => {
	test("maps primitives, enums and kinds the way qgis_sdk.ui does", () => {
		const fields = schemaFields({
			type: "object",
			properties: {
				count: { type: "integer", minimum: 1 },
				ratio: { type: "number", minimum: 0, maximum: 1 },
				on: { type: "boolean" },
				path: {
					type: "string",
					"x-qgis-sdk": { kind: "file", filters: ["*.gpkg"] },
				},
				field: { type: "string", "x-qgis-sdk": { kind: "field", of: "layer" } },
				colour: {
					type: "string",
					"x-qgis-sdk": { kind: "colour", alpha: true },
				},
			},
			required: ["count", "ratio", "on", "path"],
		});
		const kinds: FormFieldKind[] = fields.map((field) => field.kind);
		expect(kinds).toEqual([
			"integer",
			"number",
			"boolean",
			"file",
			"field",
			"colour",
		]);
		// Integer bounds are the wire's safe range, not an author's.
		expect(fields[0]?.details).toEqual({});
		expect(fields[1]?.details).toEqual({ minimum: 0, maximum: 1 });
		expect(fields[3]?.details).toEqual({ filters: ["*.gpkg"] });
		expect(fields[4]?.details).toEqual({ of: "layer" });
		expect(fields[5]?.details).toEqual({ alpha: true });
		expect(fields.map((field) => field.required)).toEqual([
			true,
			true,
			true,
			true,
			false,
			false,
		]);
	});

	test("a schema without properties has no fields", () => {
		expect(schemaFields({ type: "object" })).toEqual([]);
	});

	test("an unknown kind, a non-primitive schema and a wide union are refused by name", () => {
		expect(() =>
			schemaFields(
				{
					properties: { x: { type: "string", "x-qgis-sdk": { kind: "wat" } } },
				},
				"form demo",
			),
		).toThrow(QgisSdkStoreError);
		expect(() =>
			schemaFields({ properties: { x: { type: "array" } } }, "form demo"),
		).toThrow(/field x has no input/);
		expect(() =>
			schemaFields({
				properties: { x: { anyOf: [{ type: "string" }, { type: "number" }] } },
			}),
		).toThrow(/one type or that type plus null/);
		expect(() => schemaFields({ properties: { x: 3 } })).toThrow(
			/field x is not a schema/,
		);
	});

	test("labelFor renders a field name as a label", () => {
		expect(labelFor("buffer_distance")).toBe("Buffer distance");
		expect(labelFor("layerID")).toBe("Layerid");
	});
});

describe("FormStore", () => {
	test("refuses an unknown action and an unknown field by name", () => {
		const harness = createBridgeHarness(formSchema);
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		expect(() => new FormStore(qgis, "missing")).toThrow(
			/missing is not a declared action/,
		);
		const form = formStore(qgis, "buffer");
		expect(() => form.set("nope", 1)).toThrow(/buffer has no field nope/);
		expect(() => form.field("nope")).toThrow(QgisSdkStoreError);
		expect(form.field("mode").choices).toEqual(["fast", "exact"]);
		expect(form.title).toBe("Buffer");
		expect(FormStore.describe(qgis, "buffer")?.handler).toBe("buffer");
		expect(FormStore.describe(qgis, "missing")).toBeUndefined();
		qgis.close();
	});

	test("initial values skip undefined; a numeric field keeps a non-numeric string for validation to name", () => {
		const harness = createBridgeHarness(formSchema);
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		const form = formStore(qgis, "buffer", {
			initial: { mode: "exact", layer_id: "roads", note: undefined },
		});
		expect(form.getSnapshot().values).toEqual({
			mode: "exact",
			layer_id: "roads",
		});
		form.setValues({ distance_metres: "1.5e1", note: null });
		expect(form.getSnapshot().values).toMatchObject({
			distance_metres: 15,
			note: null,
		});
		form.set("distance_metres", "three");
		expect(form.getSnapshot().values.distance_metres).toBe("three");
		expect(form.getSnapshot().errors).toEqual({ distance_metres: "type" });
		form.set("distance_metres", "   ");
		expect(form.getSnapshot().values.distance_metres).toBe("   ");
		qgis.close();
	});

	test("abort ends a submission in flight and keeps the values", async () => {
		const harness = createBridgeHarness(formSchema);
		const reply = gate();
		harness.expectInvoke("buffer", async () => {
			await reply.promise;
			return { id: "late" };
		});
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		const form = formStore(qgis, "buffer");
		form.setValues({ layer_id: "roads", distance_metres: 1 });
		const pending = form.submit();
		await tick();
		expect(form.getSnapshot().submission.status).toBe("pending");
		form.abort();
		await expect(pending).resolves.toBeUndefined();
		reply.release();
		await tick();
		expect(form.getSnapshot()).toMatchObject({
			values: { layer_id: "roads", distance_metres: 1 },
			submission: { status: "pending" },
		});
		harness.assertSatisfied();
		qgis.close();
	});

	test("a disposed form no longer follows its submission", async () => {
		const harness = createBridgeHarness(formSchema);
		harness.expectInvoke("buffer", () => ({ id: "x" }));
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		const form = formStore(qgis, "buffer");
		form.setValues({ layer_id: "roads", distance_metres: 1 });
		form.dispose();
		await expect(form.submit()).resolves.toEqual({ id: "x" });
		expect(form.getSnapshot().submission.status).toBe("idle");
		qgis.close();
	});
});

describe("HostQueryStore", () => {
	test("a handshake the host refused is an error, not a refusal", async () => {
		const harness = createBridgeHarness(formSchema);
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		qgis.close();
		const store = new HostQueryStore(qgis, "layers.list", async () => 1);
		await expect(store.refresh()).resolves.toBeUndefined();
		expect(store.getSnapshot().status).toBe("error");
		store.reset();
		expect(store.getSnapshot()).toEqual({ status: "idle" });
	});

	test("the latest refresh wins and abort settles nothing", async () => {
		const harness = createBridgeHarness(formSchema, {
			granted: ["layers.get"],
		});
		const reply = gate();
		harness.expectInvoke("layers.get", async () => {
			await reply.promise;
			return {
				id: "a",
				name: "A",
				geometry_type: "point",
				crs: null,
				field_names: ["fid"],
			};
		});
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		const store = layerFieldsQuery(qgis, "a");
		expect(store.operation).toBe("layers.get");
		const first = store.refresh();
		await tick();
		store.abort();
		await expect(first).resolves.toBeUndefined();
		reply.release();
		await tick();
		expect(store.getSnapshot().status).toBe("loading");

		harness.expectInvoke("layers.get", () => ({
			id: "a",
			name: "A",
			geometry_type: "point",
			crs: null,
			field_names: ["fid", "name"],
		}));
		await expect(store.refresh()).resolves.toEqual(["fid", "name"]);
		harness.assertSatisfied();
		qgis.close();
	});

	test("layersQuery passes the page size through", async () => {
		const harness = createBridgeHarness(formSchema, {
			granted: ["layers.list"],
		});
		harness.expectInvoke<{ limit?: number }>("layers.list", (payload) => {
			expect(payload).toEqual({ limit: 2 });
			return { items: [], truncated: false };
		});
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		await expect(layersQuery(qgis, { pageSize: 2 }).refresh()).resolves.toEqual(
			[],
		);
		harness.assertSatisfied();
		qgis.close();
	});
});
