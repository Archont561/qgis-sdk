/**
 * The host-bound pickers against `createBridgeHarness`: layers and fields
 * load through the grant-checking queries, show the refusal without the
 * grant, and recover from a fault (task-70 AC #1).
 */

import { afterAll, describe, expect, test } from "bun:test";
import type { VectorLayerInfo } from "@archont561/qgis-sdk/host";
import { fault } from "@archont561/qgis-sdk/testing";
import { install, tick, uninstall } from "./support/dom";
import {
	expectLayer,
	expectLayers,
	RIVERS,
	ROADS,
	sdkWithHarness,
} from "./support/schema";

install();
afterAll(uninstall);

const { html } = await import("lit");
const { choose, mount, one, ui } = await import("./support/elements");

type LayerPicker = InstanceType<typeof ui.QgisLayerPicker>;
type FieldPicker = InstanceType<typeof ui.QgisFieldPicker>;

async function settled(harness: { settled(): Promise<void> }): Promise<void> {
	await harness.settled();
	await tick();
}

describe("qgis-layer-picker", () => {
	test("lists the project's layers once granted, reports the chosen id", async () => {
		const { harness, qgis } = sdkWithHarness({ granted: ["layers.list"] });
		expectLayers(harness);
		const root = await mount(
			html`<qgis-layer-picker name="layer_id" label="Layer" .qgis=${qgis}></qgis-layer-picker>`,
		);
		const seen: unknown[] = [];
		root.addEventListener("qgis-change", (event) =>
			seen.push((event as CustomEvent).detail),
		);
		await settled(harness);

		const select = one<HTMLSelectElement>(root, "select");
		expect(select.disabled).toBe(false);
		expect([...select.options].map((option) => option.textContent)).toEqual([
			"Choose a layer…",
			"roads",
			"rivers",
		]);
		choose(select, "rivers-2");
		await tick();
		expect(seen).toEqual([{ name: "layer_id", value: "rivers-2" }]);
		const picker = one<LayerPicker>(root, "qgis-layer-picker");
		expect(picker.selected).toEqual(RIVERS);
		expect(picker.value).toBe("rivers-2");
		// Once a value is chosen, the placeholder is gone unless nullable.
		expect([...select.options].map((option) => option.textContent)).toEqual([
			"roads",
			"rivers",
		]);
		harness.assertSatisfied();
		qgis.close();
	});

	test("without the grant it shows the refusal and makes no call", async () => {
		const { harness, qgis } = sdkWithHarness({ granted: [] });
		const root = await mount(
			html`<qgis-layer-picker name="layer_id" label="Layer" .qgis=${qgis}></qgis-layer-picker>`,
		);
		await settled(harness);
		const select = one<HTMLSelectElement>(root, "select");
		const error = one<HTMLElement>(root, "[data-part='error']");
		expect(select.disabled).toBe(true);
		expect(error.textContent).toBe(
			'this view was not granted layers.list; add "layers.read" to the view\'s grants',
		);
		expect(select.getAttribute("aria-describedby")).toBe(error.id);
		expect(root.querySelector("[data-part='refresh']")).toBeNull();
		expect(harness.calls.map((call) => call.kind)).toEqual(["handshake"]);
		harness.assertSatisfied();
		qgis.close();
	});

	test("a fault is shown and Refresh asks again; the geometry filter narrows", async () => {
		const { harness, qgis } = sdkWithHarness();
		harness.expectInvoke("layers.list", () => fault("internal", "boom"));
		expectLayers(harness, [
			ROADS,
			{ ...RIVERS, id: "lakes-3", name: "lakes", geometry_type: "polygon" },
		]);
		const root = await mount(
			html`<qgis-layer-picker name="layer_id" label="Layer" geometry="polygon" .qgis=${qgis}></qgis-layer-picker>`,
		);
		await settled(harness);
		expect(one<HTMLElement>(root, "[data-part='error']").textContent).toBe(
			"boom",
		);
		one<HTMLButtonElement>(root, "[data-part='refresh']").click();
		await settled(harness);
		expect(root.querySelector("[data-part='error']")).toBeNull();
		expect(
			[...one<HTMLSelectElement>(root, "select").options].map(
				(option) => option.textContent,
			),
		).toEqual(["Choose a layer…", "lakes"]);
		expect(
			one<LayerPicker>(root, "qgis-layer-picker").options.map(
				(layer) => layer.id,
			),
		).toEqual(["lakes-3"]);
		harness.assertSatisfied();
		qgis.close();
	});

	test("without an SDK it is idle: disabled, no query, refresh resolves undefined", async () => {
		const root = await mount(
			html`<qgis-layer-picker name="layer_id"></qgis-layer-picker>`,
		);
		const picker = one<LayerPicker>(root, "qgis-layer-picker");
		expect(picker.query).toBeNull();
		expect(await picker.refresh()).toBeUndefined();
		expect(one<HTMLSelectElement>(root, "select").disabled).toBe(true);
		expect(one<HTMLButtonElement>(root, "[data-part='refresh']").disabled).toBe(
			true,
		);
	});

	test("a loading query shows a status line", async () => {
		const { harness, qgis } = sdkWithHarness();
		let release: (() => void) | null = null;
		harness.expectInvoke<
			Record<string, never>,
			{ items: VectorLayerInfo[]; truncated: boolean }
		>(
			"layers.list",
			() =>
				new Promise((resolve) => {
					release = () => resolve({ items: [ROADS], truncated: false });
				}),
		);
		const root = await mount(
			html`<qgis-layer-picker .qgis=${qgis}></qgis-layer-picker>`,
		);
		await settled(harness);
		expect(one<HTMLElement>(root, "[data-part='status']").textContent).toBe(
			"Loading layers…",
		);
		expect(
			one<HTMLSelectElement>(root, "select").getAttribute("aria-busy"),
		).toBe("true");
		(release as unknown as () => void)();
		await settled(harness);
		expect(root.querySelector("[data-part='status']")).toBeNull();
		harness.assertSatisfied();
		qgis.close();
	});
});

describe("qgis-field-picker", () => {
	test("waits for a layer, then lists its fields; a new layer reloads", async () => {
		const { harness, qgis } = sdkWithHarness();
		const root = await mount(
			html`<qgis-field-picker name="field_name" label="Field" nullable .qgis=${qgis}></qgis-field-picker>`,
		);
		const seen: unknown[] = [];
		root.addEventListener("qgis-change", (event) =>
			seen.push((event as CustomEvent).detail),
		);
		const picker = one<FieldPicker>(root, "qgis-field-picker");
		const select = one<HTMLSelectElement>(root, "select");
		expect(select.disabled).toBe(true);
		expect(select.options[0]?.textContent).toBe("Choose a layer first");
		expect(picker.query).toBeNull();

		expectLayer(harness, ROADS);
		picker.layer = ROADS.id;
		await settled(harness);
		expect([...select.options].map((option) => option.textContent)).toEqual([
			"Choose a field…",
			"name",
			"surface",
		]);
		choose(select, "surface");
		expect(seen).toEqual([{ name: "field_name", value: "surface" }]);

		expectLayer(harness, RIVERS);
		picker.layer = RIVERS.id;
		await settled(harness);
		expect(picker.options).toEqual(["name", "length"]);
		// The old value is no longer offered, so the placeholder is selected.
		expect(one<HTMLOptionElement>(select, "option[selected]").value).toBe("");
		choose(select, "");
		expect(seen.at(-1)).toEqual({ name: "field_name", value: null });
		harness.assertSatisfied();
		qgis.close();
	});

	test("without the grant it shows the refusal; a fault its message", async () => {
		const refused = sdkWithHarness({ granted: [] });
		const root = await mount(
			html`<qgis-field-picker name="f" .qgis=${refused.qgis} .layer=${ROADS.id}></qgis-field-picker>`,
		);
		await settled(refused.harness);
		expect(one<HTMLElement>(root, "[data-part='error']").textContent).toContain(
			"not granted layers.get",
		);
		expect(refused.harness.calls.map((call) => call.kind)).toEqual([
			"handshake",
		]);
		refused.qgis.close();

		const faulty = sdkWithHarness();
		faulty.harness.expectInvoke("layers.get", () => fault("not_found", "gone"));
		const picker = one<FieldPicker>(root, "qgis-field-picker");
		picker.qgis = faulty.qgis;
		await settled(faulty.harness);
		expect(one<HTMLElement>(root, "[data-part='error']").textContent).toBe(
			"gone",
		);
		expect(await picker.refresh()).toBeUndefined();
		faulty.qgis.close();
	});
});
