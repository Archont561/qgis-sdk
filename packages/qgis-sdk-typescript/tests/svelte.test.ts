/**
 * The behaviour suite through the Svelte adapter, plus what only the adapter
 * adds: `setQgisSdk`/`getQgisSdk` across a mounted component tree, `$store`
 * reads of the core stores, and `toRune`.
 *
 * Svelte components are compiled at test time: a Bun plugin registered below
 * hands `.svelte` files to `svelte/compiler`. Bun resolves `svelte` to its
 * server build (no `browser` condition under `bun test`), where `mount` is
 * unavailable, so the same plugin swaps the two server entry modules for the
 * client ones. Both happen before the dynamic imports that need them.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { plugin } from "bun";
import { compile } from "svelte/compiler";
import { QgisSdk } from "../src/qgis-sdk";
import {
	type FormState,
	type HostQueryState,
	layersQuery,
	type OperationState,
	type Store,
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
	formSchema,
} from "./store-behaviour";
import { container, install, uninstall } from "./support/dom";

install();

plugin({
	name: "svelte-fixtures",
	setup(build) {
		build.onLoad(
			{ filter: /[\\/]svelte[\\/]src[\\/](store[\\/])?index-server\.js$/ },
			() => ({
				contents: 'export * from "./index-client.js";\n',
				loader: "js",
			}),
		);
		build.onLoad({ filter: /\.svelte$/ }, async (args) => {
			const source = await Bun.file(args.path).text();
			const { js } = compile(source, {
				filename: args.path,
				generate: "client",
			});
			return { contents: js.code, loader: "js" };
		});
	},
});

const { flushSync, mount, unmount } = await import("svelte");
const { get } = await import("svelte/store");
const adapter = await import("../src/svelte");
const { default: Host } = await import("./svelte/Host.svelte");
const { default: Page } = await import("./svelte/Page.svelte");
const { default: Watch } = await import("./svelte/Watch.svelte");

function follow<T>(store: Store<T>): {
	history: T[];
	current(): T;
	stop(): void;
} {
	const history: T[] = [];
	const stop = store.subscribe((snapshot) => history.push(snapshot));
	return { history, current: () => get(store), stop };
}

/** Run `setup` inside a component, so `onDestroy` has one to attach to. */
function host<T>(setup: () => T): { value: T; destroy(): void } {
	let value: T | undefined;
	const app = mount(Host, {
		target: container(),
		props: {
			setup: () => {
				value = setup();
			},
		},
	});
	return {
		value: value as T,
		destroy: () => {
			unmount(app);
		},
	};
}

const tick = (): Promise<void> =>
	new Promise((resolve) => setTimeout(resolve, 0));

const svelte: Driver = {
	async operation(operation) {
		const { value: store, destroy } = host(() => adapter.operation(operation));
		const seen = follow<OperationState<unknown>>(store);
		return {
			history: seen.history as never,
			current: seen.current as never,
			run: store.run as never,
			abort: store.abort,
			reset: store.reset,
			dispose: async () => {
				seen.stop();
				destroy();
			},
		};
	},
	async stream(open, input, handlers) {
		const { value: store, destroy } = host(() =>
			adapter.stream(open, input, handlers),
		);
		const seen = follow<StreamState<unknown>>(store);
		return {
			history: seen.history as never,
			current: seen.current as never,
			setInput: async (next) => {
				store.setInput(next);
			},
			setHandlers: async (next) => {
				store.setHandlers(next);
			},
			dispose: async () => {
				seen.stop();
				destroy();
			},
		};
	},
	async form(qgis, id, options) {
		const { value: store, destroy } = host(() =>
			adapter.form(qgis, id, options),
		);
		const seen = follow<FormState<unknown>>(store);
		return {
			history: seen.history as never,
			current: seen.current as never,
			fields: store.fields,
			set: async (name, value) => {
				store.set(name, value);
			},
			submit: store.submit as never,
			reset: async () => {
				store.reset();
			},
			dispose: async () => {
				seen.stop();
				destroy();
			},
		};
	},
	async layers(qgis) {
		const { value: store, destroy } = host(() =>
			adapter.hostQuery(layersQuery(qgis), { auto: false }),
		);
		const seen = follow<HostQueryState<unknown>>(store);
		return {
			history: seen.history as never,
			current: seen.current as never,
			refresh: store.refresh,
			dispose: async () => {
				seen.stop();
				destroy();
			},
		};
	},
	settle: tick,
};

afterAll(uninstall);

describeStoreBehaviour("svelte", svelte);

describe("svelte: what the adapter adds", () => {
	test("getQgisSdk outside setQgisSdk is a typed error", () => {
		expect(() => host(() => adapter.getQgisSdk())).toThrow(
			adapter.QgisSdkBridgeSvelteError,
		);
	});

	test("a mounted tree shares one QgisSdk, renders a form from $form and a rune, and submits through it", async () => {
		const harness = createBridgeHarness(formSchema);
		harness.expectInvoke("buffer", (payload) => ({ id: payload.layer_id }));
		const qgis = QgisSdk.fromBridgeSchema(formSchema, { transport: harness });
		const target = container();
		interface Ready {
			readonly qgis: unknown;
			readonly buffer: { submit(): Promise<unknown> };
		}
		const readies: Ready[] = [];
		const app = mount(Page, {
			target,
			props: {
				qgis,
				initial: { layer_id: "roads", distance_metres: 1 },
				onReady: (value: Ready) => {
					readies.push(value);
				},
			},
		});
		const formElement = target.querySelector("form");
		expect(formElement?.getAttribute("data-valid")).toBe("true");
		expect(formElement?.getAttribute("data-rune-valid")).toBe("true");
		expect(
			[...target.querySelectorAll("label")].map((label) => label.textContent),
		).toEqual(["Layer id", "Distance metres", "Note", "Mode"]);
		const seen = readies[0] as Ready;
		expect(seen.qgis).toBe(qgis);
		expect(target.querySelector("output")?.textContent).toBe("idle");

		await expect(seen.buffer.submit()).resolves.toEqual({ id: "roads" });
		flushSync();
		expect(target.querySelector("output")?.textContent).toBe("ok");
		harness.assertSatisfied();
		unmount(app);
		qgis.close();
	});

	test("a stream store follows a reactive input through $effect and closes with the component", async () => {
		const harness = createBridgeHarness<"sites.summary" | "sites.watch">();
		harness.expectSubscribe("sites.watch", () => {});
		harness.expectSubscribe("sites.watch", () => {});
		const qgis = QgisSdk.fromBridgeSchema<Operations, Streams>(schema, {
			transport: harness,
		});
		const target = container();
		const app = mount(Watch, {
			target,
			props: { open: qgis.sites.watch, initial: "a" },
		}) as { setLayer(id: string | null): void };
		flushSync();
		await tick();
		flushSync();
		expect(target.querySelector("i")?.textContent).toBe("open");
		expect(harness.openSubscriptions).toHaveLength(1);

		app.setLayer("b");
		flushSync();
		await tick();
		await harness.settled();
		expect(
			harness.calls.filter((call) => call.kind === "subscribe"),
		).toHaveLength(2);
		expect(harness.openSubscriptions).toHaveLength(1);

		unmount(app);
		await harness.settled();
		expect(harness.openSubscriptions).toEqual([]);
		harness.assertSatisfied();
		qgis.close();
	});
});
