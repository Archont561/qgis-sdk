/**
 * The wrapper behaviour suite through `./vue`, plus what only Vue adds:
 * `.prop` bindings for objects, re-emitted events, `components` for a
 * registration loop.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { container, install, uninstall } from "./support/dom";
import {
	describeWrapperBehaviour,
	type MountedWrapper,
	type WrapperCallbacks,
	type WrapperDriver,
} from "./wrapper-behaviour";

install();
afterAll(uninstall);

const { createApp, h, nextTick, resolveComponent, shallowRef } = await import(
	"vue"
);
const wrappers = await import("../src/vue");

function listeners(on: WrapperCallbacks): Record<string, unknown> {
	return {
		onChange: on.change,
		onResult: on.result,
		onRun: on.run,
		onCancel: on.cancel,
	};
}

const driver: WrapperDriver = {
	name: "Vue",
	async mount(tag, props, on = {}): Promise<MountedWrapper> {
		const component = wrappers.components[tag];
		if (component === undefined) {
			throw new Error(`no Vue wrapper for ${tag}`);
		}
		const root = container();
		const current = shallowRef<Record<string, unknown>>({ ...props });
		const app = createApp({
			render: () => h(component, { ...current.value, ...listeners(on) }),
		});
		app.mount(root);
		await nextTick();
		return {
			root,
			update: async (next) => {
				current.value = { ...current.value, ...next };
				await nextTick();
			},
			dispose: async () => {
				app.unmount();
				await nextTick();
			},
		};
	},
	async settle() {
		await nextTick();
	},
};

describeWrapperBehaviour(driver);

describe("Vue specifics", () => {
	test("every tag has a component named after it, registrable in a loop", async () => {
		expect(Object.keys(wrappers.components)).toHaveLength(11);
		expect(wrappers.QgisLayerPicker.name).toBe("QgisLayerPicker");
		const root = container();
		const app = createApp({
			render: () =>
				h("div", [
					h(resolveComponent("qgis-distance-wrapped"), {
						name: "d",
						label: "Distance",
						value: 7,
						unit: "km",
					}),
					h(wrappers.QgisLogView, { lines: ["a", "b"] }),
				]),
		});
		for (const [tag, component] of Object.entries(wrappers.components)) {
			app.component(`${tag}-wrapped`, component);
		}
		app.mount(root);
		await nextTick();
		const input = root.querySelector("qgis-distance input") as HTMLInputElement;
		expect(input).not.toBeNull();
		expect(input.value).toBe("7");
		expect(
			root.querySelector("qgis-distance [data-part='unit']")?.textContent,
		).toBe("km");
		expect(root.querySelector("qgis-log-view pre")?.textContent).toBe("a\nb");
		app.unmount();
	});
});
