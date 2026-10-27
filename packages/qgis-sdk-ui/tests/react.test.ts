/**
 * The wrapper behaviour suite through `./react`, plus what only React adds:
 * `createComponent` props typed by the element, a `ref` to the element.
 *
 * Bun resolves `@lit/react` through its `node` export condition, the
 * server-rendering build that sets no properties and attaches no listeners
 * (the browser does that after hydration). The tests want the browser
 * build, which a bundler picks for a page, so a Bun plugin registered below
 * resolves the package to it before the dynamic import.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { install, uninstall } from "./support/dom";
import {
	describeWrapperBehaviour,
	type MountedWrapper,
	type WrapperCallbacks,
	type WrapperDriver,
} from "./wrapper-behaviour";

install();
afterAll(uninstall);
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;

const React = await import("react");
const { act, createElement, createRef } = React;
const { createRoot } = await import("react-dom/client");
const wrappers = await import("../src/react");
const { container } = await import("./support/dom");

type Wrapper = (typeof wrappers)[keyof typeof wrappers];

const COMPONENTS: Readonly<Record<string, Wrapper>> = {
	"qgis-form": wrappers.QgisForm,
	"qgis-layer-picker": wrappers.QgisLayerPicker,
	"qgis-job-progress": wrappers.QgisJobProgress,
	"qgis-choice": wrappers.QgisChoice,
};

function callbacks(on: WrapperCallbacks): Record<string, unknown> {
	return {
		onQgisChange:
			on.change === undefined
				? undefined
				: (event: CustomEvent) => on.change?.(event.detail),
		onQgisResult:
			on.result === undefined
				? undefined
				: (event: CustomEvent) => on.result?.(event.detail),
		onQgisRun: on.run,
		onQgisCancel: on.cancel,
	};
}

const driver: WrapperDriver = {
	name: "React",
	async mount(tag, props, on = {}): Promise<MountedWrapper> {
		const component = COMPONENTS[tag];
		if (component === undefined) {
			throw new Error(`no React wrapper for ${tag} in this test`);
		}
		const root = container();
		const reactRoot = createRoot(root);
		let current = { ...props };
		const render = async (): Promise<void> => {
			await act(async () => {
				reactRoot.render(
					createElement(
						component as React.ComponentType<Record<string, unknown>>,
						{
							...current,
							...callbacks(on),
						},
					),
				);
			});
		};
		await render();
		return {
			root,
			update: async (next) => {
				current = { ...current, ...next };
				await render();
			},
			dispose: async () => {
				await act(async () => {
					reactRoot.unmount();
				});
			},
		};
	},
	async settle() {
		await act(async () => {});
	},
};

describeWrapperBehaviour(driver);

describe("React specifics", () => {
	test("a ref reaches the element and the display name is the class", async () => {
		const root = container();
		const reactRoot = createRoot(root);
		const ref =
			createRef<InstanceType<typeof import("../src/index").QgisDistance>>();
		await act(async () => {
			reactRoot.render(
				createElement(wrappers.QgisDistance, {
					ref,
					name: "d",
					label: "Distance",
					value: 4,
					unit: "km",
				}),
			);
		});
		expect(ref.current?.localName).toBe("qgis-distance");
		expect(ref.current?.value).toBe(4);
		expect(root.querySelector("input")?.value).toBe("4");
		expect(wrappers.QgisDistance.displayName).toBe("QgisDistance");
		await act(async () => {
			reactRoot.unmount();
		});
	});
});
