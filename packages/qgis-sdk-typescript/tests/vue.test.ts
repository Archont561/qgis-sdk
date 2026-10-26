/** biome-ignore-all lint/correctness/useHookAtTopLevel: Vue composables share React's `use` prefix and are called from `setup()`, not from a React component. */
/**
 * The behaviour suite through the Vue adapter, plus what only the adapter
 * adds: `provideQgisSdk`/`useQgisSdk` across a mounted component tree, and
 * the scope teardown each composable relies on.
 */

import { describe, expect, test } from "bun:test";
import { QgisSdk } from "../src/qgis-sdk";
import {
	type FormState,
	type HostQueryState,
	layersQuery,
	type OperationState,
	type StreamState,
} from "../src/stores";
import { createBridgeHarness } from "../src/testing";
import schema, {
	type Operations,
	type Streams,
} from "./contracts/generated/clients/sites.schema";
import {
	type Driver,
	describeStoreBehaviour,
	type FormOperations,
	formSchema,
} from "./store-behaviour";
import { container } from "./support/dom";

// Vue's DOM renderer reads `document` when its module is evaluated, and Bun
// evaluates a package import before a relative one whatever the source order;
// the dynamic imports run after `./support/dom` installed the window.
const {
	createApp,
	defineComponent,
	effectScope,
	h,
	nextTick,
	ref,
	shallowRef,
} = await import("vue");
const {
	provideQgisSdk,
	QgisSdkBridgeVueError,
	useForm,
	useHostQuery,
	useOperation,
	useQgisSdk,
	useStream,
} = await import("../src/vue");

/** Record each snapshot a shallow ref took, through a watcher-free subscribe. */
function follow<T>(store: {
	subscribe(listener: (snapshot: T) => void): () => void;
}): { history: T[]; current(): T; stop(): void } {
	const history: T[] = [];
	const stop = store.subscribe((snapshot) => history.push(snapshot));
	return { history, current: () => history.at(-1) as T, stop };
}

const settle = async (): Promise<void> => {
	await new Promise((resolve) => setTimeout(resolve, 0));
	await nextTick();
};

/** Every composable runs inside an effect scope, as it would in `setup()`. */
const vue: Driver = {
	async operation(operation) {
		const scope = effectScope();
		const bound = scope.run(() => useOperation(operation));
		if (bound === undefined) {
			throw new Error("the scope did not run");
		}
		const seen = follow<OperationState<unknown>>(bound.store);
		return {
			history: seen.history as never,
			current: () => bound.state.value as never,
			run: bound.run as never,
			abort: bound.abort,
			reset: bound.reset,
			dispose: async () => {
				seen.stop();
				scope.stop();
			},
		};
	},
	async stream(open, input, handlers) {
		const scope = effectScope();
		const inputRef = shallowRef(input);
		const current = scope.run(() => useStream(open, inputRef, handlers));
		if (current === undefined) {
			throw new Error("the scope did not run");
		}
		const seen = follow<StreamState<unknown>>(current.store);
		return {
			history: seen.history as never,
			current: () => current.value as never,
			setInput: async (next) => {
				inputRef.value = next;
				await nextTick();
			},
			setHandlers: async (next) => {
				current.store.setHandlers(next);
			},
			dispose: async () => {
				seen.stop();
				scope.stop();
			},
		};
	},
	async form(qgis, id, options) {
		const scope = effectScope();
		const bound = scope.run(() => useForm(qgis, id, options));
		if (bound === undefined) {
			throw new Error("the scope did not run");
		}
		const seen = follow<FormState<unknown>>(bound.form);
		return {
			history: seen.history as never,
			current: () => bound.state.value as never,
			fields: bound.form.fields,
			set: async (name, value) => {
				bound.form.set(name, value);
				await nextTick();
			},
			submit: bound.form.submit as never,
			reset: async () => {
				bound.form.reset();
				await nextTick();
			},
			dispose: async () => {
				seen.stop();
				scope.stop();
			},
		};
	},
	async layers(qgis) {
		const scope = effectScope();
		const bound = scope.run(() =>
			useHostQuery(layersQuery(qgis), { auto: false }),
		);
		if (bound === undefined) {
			throw new Error("the scope did not run");
		}
		const seen = follow<HostQueryState<unknown>>(bound.query);
		return {
			history: seen.history as never,
			current: () => bound.state.value as never,
			refresh: bound.query.refresh,
			dispose: async () => {
				seen.stop();
				scope.stop();
			},
		};
	},
	settle,
};

describeStoreBehaviour("vue", vue);

describe("vue: what the adapter adds", () => {
	test("useQgisSdk outside a provider is a typed error", () => {
		const scope = effectScope();
		expect(() => scope.run(() => useQgisSdk())).toThrow(QgisSdkBridgeVueError);
		scope.stop();
	});

	test("a mounted tree shares one QgisSdk, renders a form from its fields and submits through it", async () => {
		const harness = createBridgeHarness(formSchema);
		harness.expectInvoke("buffer", (payload) => ({ id: payload.layer_id }));
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		let submit: (() => Promise<unknown>) | null = null;
		const Form = defineComponent({
			setup() {
				const sdk = useQgisSdk<FormOperations, Record<never, never>>();
				expect(sdk).toBe(qgis);
				const { state, form } = useForm(sdk, "buffer", {
					initial: { layer_id: "roads", distance_metres: 1 },
				});
				submit = form.submit;
				return () =>
					h(
						"form",
						{ "data-valid": String(state.value.valid) },
						form.fields.map((field) =>
							h("label", { key: field.name }, field.label),
						),
					);
			},
		});
		const Page = defineComponent({
			setup() {
				provideQgisSdk(qgis);
				return () => h(Form);
			},
		});
		const root = container();
		const app = createApp(Page);
		app.mount(root);
		expect(root.querySelector("form")?.getAttribute("data-valid")).toBe("true");
		expect(
			[...root.querySelectorAll("label")].map((label) => label.textContent),
		).toEqual(["Layer id", "Distance metres", "Note", "Mode"]);

		await expect(
			(submit as unknown as () => Promise<unknown>)(),
		).resolves.toEqual({ id: "roads" });
		harness.assertSatisfied();
		app.unmount();
		qgis.close();
	});

	test("useStream follows a ref and a getter, and unmounting the component closes the stream", async () => {
		const harness = createBridgeHarness<"sites.summary" | "sites.watch">();
		harness.expectSubscribe("sites.watch", () => {});
		harness.expectSubscribe("sites.watch", () => {});
		const qgis = QgisSdk.fromBridgeSchema<Operations, Streams>(schema, {
			transport: harness,
		});
		const layerId = ref<string | null>("a");
		let status = "";
		const View = defineComponent({
			setup() {
				const state = useStream(qgis.sites.watch, () =>
					layerId.value === null ? null : { layer_id: layerId.value },
				);
				return () => {
					status = state.value.status;
					return h("i", status);
				};
			},
		});
		const app = createApp(View);
		app.mount(container());
		await settle();
		expect(status).toBe("open");
		expect(harness.openSubscriptions).toHaveLength(1);

		layerId.value = "b";
		await settle();
		await harness.settled();
		expect(
			harness.calls.filter((call) => call.kind === "subscribe"),
		).toHaveLength(2);
		expect(harness.openSubscriptions).toHaveLength(1);

		app.unmount();
		await harness.settled();
		expect(harness.openSubscriptions).toEqual([]);
		harness.assertSatisfied();
		qgis.close();
	});

	test("useHostQuery refreshes at once by default and the scope's end aborts it", async () => {
		const harness = createBridgeHarness(formSchema, { granted: [] });
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		const scope = effectScope();
		const bound = scope.run(() => useHostQuery(layersQuery(qgis)));
		await settle();
		expect(bound?.state.value).toMatchObject({ status: "refused" });
		scope.stop();
		qgis.close();
	});
});
