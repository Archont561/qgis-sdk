/**
 * The wrapper behaviour suite through `./svelte`, plus what only Svelte
 * adds: `use:qgisProps` over a `<svelte:element>`, and Svelte's own property
 * setting on a registered element without the action.
 *
 * Svelte components are compiled at test time: a Bun plugin registered below
 * hands `.svelte` files to `svelte/compiler`. The package's tests run with
 * `--conditions=browser`, so `svelte` resolves to its client build and
 * `mount` is available without a module swap.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { plugin } from "bun";
import { compile } from "svelte/compiler";
import { container, install, uninstall } from "./support/dom";
import { expectLayers, ROADS, sdkWithHarness } from "./support/schema";
import {
	describeWrapperBehaviour,
	type MountedWrapper,
	type WrapperDriver,
} from "./wrapper-behaviour";

install();
afterAll(uninstall);

plugin({
	name: "svelte-fixtures",
	setup(build) {
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
const svelte = await import("../src/svelte");
const { default: Element } = await import("./svelte/Element.svelte");
const { default: Native } = await import("./svelte/Native.svelte");

const driver: WrapperDriver = {
	name: "Svelte",
	async mount(tag, props, on = {}): Promise<MountedWrapper> {
		const root = container();
		const app = mount(Element, { target: root, props: { tag, props, on } }) as {
			update(next: Record<string, unknown>): void;
		};
		flushSync();
		return {
			root,
			update: async (next) => {
				app.update(next);
				flushSync();
			},
			dispose: async () => {
				await unmount(app);
			},
		};
	},
	async settle() {
		flushSync();
	},
};

describeWrapperBehaviour(driver);

describe("Svelte specifics", () => {
	test("the event names are the on* attributes; qgisProps skips undefined and repeats", () => {
		expect(svelte.ON).toEqual({
			change: "onqgis-change",
			result: "onqgis-result",
			run: "onqgis-run",
			cancel: "onqgis-cancel",
		});
		expect(svelte.EVENT_NAMES.change).toBe("qgis-change");
		const node = document.createElement("qgis-distance") as HTMLElement & {
			value: number | null;
			unit: string;
		};
		const action = svelte.qgisProps(node, { value: 3, unit: undefined });
		expect(node.value).toBe(3);
		expect(node.unit).toBe("m");
		action.update?.({ value: 3, unit: "km" });
		expect(node.unit).toBe("km");
	});

	test("Svelte sets properties on a registered element without the action", async () => {
		const { harness, qgis } = sdkWithHarness({ granted: ["layers.list"] });
		expectLayers(harness);
		const root = container();
		const changes: unknown[] = [];
		const app = mount(Native, {
			target: root,
			props: {
				qgis,
				value: ROADS.id,
				onchange: (event: CustomEvent) => changes.push(event.detail),
			},
		});
		flushSync();
		await harness.settled();
		await new Promise((resolve) => setTimeout(resolve, 0));
		const select = root.querySelector("select") as HTMLSelectElement;
		expect(select.disabled).toBe(false);
		expect(
			(root.querySelector("option[selected]") as HTMLOptionElement).value,
		).toBe(ROADS.id);
		select.value = "rivers-2";
		select.dispatchEvent(new Event("change", { bubbles: true }));
		expect(changes).toEqual([{ name: "layer_id", value: "rivers-2" }]);
		await unmount(app);
		harness.assertSatisfied();
		qgis.close();
	});
});
