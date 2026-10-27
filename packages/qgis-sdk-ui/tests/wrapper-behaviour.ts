/**
 * The one behaviour suite every wrapper must pass (task-70 AC #1).
 *
 * The elements own the behaviour; a wrapper only forwards properties and
 * events. So the suite is written once against a `WrapperDriver` - "mount
 * this tag with these props and callbacks, update, dispose" - and
 * `tests/react.test.ts`, `tests/vue.test.ts` and `tests/svelte.test.ts` each
 * run it through their own driver. A behaviour that holds for the elements
 * and fails for one wrapper is a wrapper bug.
 */

import { describe, expect, test } from "bun:test";
import { formStore } from "@archont561/qgis-sdk";
import { tick } from "./support/dom";
import { expectLayers, RIVERS, ROADS, sdkWithHarness } from "./support/schema";

/** Callbacks a wrapper exposes for the elements' events. */
export interface WrapperCallbacks {
	readonly change?: (detail: unknown) => void;
	readonly result?: (detail: unknown) => void;
	readonly run?: () => void;
	readonly cancel?: () => void;
}

export interface MountedWrapper {
	/** The container the element was rendered into. */
	readonly root: HTMLElement;
	/** Re-render with these props over the previous ones. */
	update(props: Record<string, unknown>): Promise<void>;
	/** Unmount, the way the framework does on teardown. */
	dispose(): Promise<void>;
}

export interface WrapperDriver {
	readonly name: string;
	mount(
		tag: string,
		props: Record<string, unknown>,
		on?: WrapperCallbacks,
	): Promise<MountedWrapper>;
	/** Let the framework's queued renders land. */
	settle(): Promise<void>;
}

function one<T extends Element>(root: ParentNode, selector: string): T {
	const found = root.querySelector<T>(selector);
	if (found === null) {
		throw new Error(`no ${selector} under the container`);
	}
	return found;
}

function choose(select: HTMLSelectElement, value: string): void {
	select.value = value;
	select.dispatchEvent(new Event("change", { bubbles: true }));
}

export function describeWrapperBehaviour(driver: WrapperDriver): void {
	const settle = async (harness?: {
		settled(): Promise<void>;
	}): Promise<void> => {
		await harness?.settled();
		await tick();
		await driver.settle();
	};

	describe(`${driver.name} wrapper`, () => {
		test("forwards object props, re-renders on update, reports qgis-change, disposes", async () => {
			const { harness, qgis } = sdkWithHarness({ granted: ["layers.list"] });
			expectLayers(harness);
			const changes: unknown[] = [];
			const mounted = await driver.mount(
				"qgis-layer-picker",
				{ qgis, name: "layer_id", label: "Layer", nullable: true },
				{ change: (detail) => changes.push(detail) },
			);
			await settle(harness);
			const picker = one<HTMLElement & { value: string | null }>(
				mounted.root,
				"qgis-layer-picker",
			);
			expect(picker.dataset.qgisSdk).toBe("layer_id");
			expect(picker.shadowRoot).toBeNull();
			const select = one<HTMLSelectElement>(mounted.root, "select");
			expect([...select.options].map((option) => option.textContent)).toEqual([
				"Choose a layer…",
				"roads",
				"rivers",
			]);
			expect(one<HTMLLabelElement>(mounted.root, "label").htmlFor).toBe(
				select.id,
			);

			choose(select, ROADS.id);
			await settle();
			expect(changes).toEqual([{ name: "layer_id", value: ROADS.id }]);

			await mounted.update({ value: RIVERS.id, label: "Which layer" });
			await settle();
			expect(picker.value).toBe(RIVERS.id);
			expect(one<HTMLOptionElement>(select, "option[selected]").value).toBe(
				RIVERS.id,
			);
			expect(one<HTMLLabelElement>(mounted.root, "label").textContent).toBe(
				"Which layer",
			);

			await mounted.dispose();
			await settle();
			expect(mounted.root.querySelector("qgis-layer-picker")).toBeNull();
			harness.assertSatisfied();
			qgis.close();
		});

		test("shows the refusal without the grant and makes no call", async () => {
			const { harness, qgis } = sdkWithHarness({ granted: [] });
			const mounted = await driver.mount("qgis-layer-picker", {
				qgis,
				name: "layer_id",
			});
			await settle(harness);
			expect(
				one<HTMLElement>(mounted.root, "[data-part='error']").textContent,
			).toContain("not granted layers.list");
			expect(one<HTMLSelectElement>(mounted.root, "select").disabled).toBe(
				true,
			);
			expect(harness.calls.map((call) => call.kind)).toEqual(["handshake"]);
			await mounted.dispose();
			qgis.close();
		});

		test("a form submits through its run button and reports run and result", async () => {
			const { harness, qgis } = sdkWithHarness({ granted: [] });
			harness.expectInvoke("buffer", (payload) => ({
				id: `done:${payload.layer_id}`,
			}));
			const store = formStore(qgis, "buffer", {
				initial: { layer_id: ROADS.id, distance_metres: 3 },
			});
			const events: unknown[] = [];
			const mounted = await driver.mount(
				"qgis-form",
				{ store, qgis, submitLabel: "Buffer now" },
				{
					run: () => events.push("run"),
					result: (detail) => events.push(detail),
				},
			);
			await settle(harness);
			expect(mounted.root.querySelectorAll("[data-field]")).toHaveLength(
				store.fields.length,
			);
			const button = one<HTMLButtonElement>(
				mounted.root,
				"qgis-run-button button",
			);
			expect(button.textContent).toBe("Buffer now");
			button.click();
			await settle(harness);
			expect(events).toEqual(["run", { id: `done:${ROADS.id}` }]);
			await mounted.dispose();
			harness.assertSatisfied();
			qgis.close();
		});

		test("a progress bar follows prop updates and reports cancel", async () => {
			const cancels: string[] = [];
			const mounted = await driver.mount(
				"qgis-job-progress",
				{
					status: "pending",
					fraction: 0.5,
					message: "Half",
					cancel: () => cancels.push("prop"),
				},
				{ cancel: () => cancels.push("event") },
			);
			await settle();
			const bar = one<HTMLProgressElement>(mounted.root, "progress");
			expect(bar.getAttribute("value")).toBe("0.5");
			expect(one<HTMLOutputElement>(mounted.root, "output").textContent).toBe(
				"Half",
			);
			one<HTMLButtonElement>(mounted.root, "[data-part='cancel']").click();
			await settle();
			expect(cancels).toEqual(["event", "prop"]);
			await mounted.update({ status: "ok", fraction: 1, message: "" });
			await settle();
			expect(bar.getAttribute("value")).toBe("1");
			expect(one<HTMLOutputElement>(mounted.root, "output").textContent).toBe(
				"Done",
			);
			expect(mounted.root.querySelector("[data-part='cancel']")).toBeNull();
			await mounted.dispose();
		});

		test("a choice keeps the type of its value through the wrapper", async () => {
			const changes: unknown[] = [];
			const mounted = await driver.mount(
				"qgis-choice",
				{ name: "n", choices: [1, 2, 3], value: 2 },
				{ change: (detail) => changes.push(detail) },
			);
			await settle();
			const select = one<HTMLSelectElement>(mounted.root, "select");
			expect(
				one<HTMLOptionElement>(select, "option[selected]").textContent,
			).toBe("2");
			choose(select, "2");
			await settle();
			expect(changes).toEqual([{ name: "n", value: 3 }]);
			await mounted.dispose();
		});
	});
}
