/**
 * The keyword forms shared with the Python catalogue (TASK-108 AC #4): a
 * component reads the same on both sides for the names both have.
 * `Choice(options=)` is `.options`, `Input(required=)` is `required`,
 * `JobProgress(cancellable=)` is `cancellable`, `Button(text=)` is `.text`,
 * and `FieldPicker(of=picker)` is `.of=${picker}`.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { install, tick, uninstall } from "./support/dom";
import {
	expectLayer,
	expectLayers,
	ROADS,
	sdkWithHarness,
} from "./support/schema";

install();
afterAll(uninstall);

const { html } = await import("lit");
const { choose, mount, one, ui } = await import("./support/elements");
const { ELEMENT_PROPS } = await import("../src/events");

type Choice = InstanceType<typeof ui.QgisChoice>;
type RunButton = InstanceType<typeof ui.QgisRunButton>;
type FieldPicker = InstanceType<typeof ui.QgisFieldPicker>;
type LayerPicker = InstanceType<typeof ui.QgisLayerPicker>;

describe("ELEMENT_PROPS", () => {
	test("names every reactive property of every element, so the wrappers forward them", () => {
		for (const [tag, element] of Object.entries(ui.ELEMENTS)) {
			const declared = [
				...(
					element as unknown as {
						elementProperties: Map<string, unknown>;
					}
				).elementProperties.keys(),
			];
			const forwarded = ELEMENT_PROPS[tag] ?? [];
			expect({
				tag,
				missing: declared.filter((p) => !forwarded.includes(p)),
			}).toEqual({ tag, missing: [] });
		}
	});
});

describe("Choice(options=)", () => {
	test("`options` and `choices` are one list, in either spelling", async () => {
		const root = await mount(
			html`<qgis-choice name="mode" label="Mode" .options=${["fast", "safe"]}></qgis-choice>`,
		);
		const element = one<Choice>(root, "qgis-choice");
		expect(element.choices).toEqual(["fast", "safe"]);
		expect(
			[...root.querySelectorAll("option")].map((option) => option.textContent),
		).toEqual(["Choose…", "fast", "safe"]);

		element.choices = ["slow"];
		await tick();
		expect(element.options).toEqual(["slow"]);
		expect(
			[...root.querySelectorAll("option")].map((option) => option.textContent),
		).toEqual(["Choose…", "slow"]);
	});
});

describe("Input(required=)", () => {
	test("marks the control required on every input element, off by default", async () => {
		const root = await mount(html`
			<qgis-choice name="mode" .options=${["a"]} required></qgis-choice>
			<qgis-distance name="d" required></qgis-distance>
			<qgis-crs-picker name="crs" required></qgis-crs-picker>
			<qgis-file-input name="out" required></qgis-file-input>
			<qgis-directory-input name="dir" required></qgis-directory-input>
			<qgis-layer-picker name="layer" required></qgis-layer-picker>
			<qgis-field-picker name="field" required></qgis-field-picker>
			<qgis-distance name="free"></qgis-distance>
		`);
		const controls = "[data-part='control'][required]";
		const required = [...root.querySelectorAll(controls)].map((element) =>
			element.getAttribute("name"),
		);
		expect(required).toEqual([
			"mode",
			"d",
			"crs",
			"out",
			"dir",
			"layer",
			"field",
		]);
		for (const control of root.querySelectorAll(controls)) {
			expect(control.getAttribute("aria-required")).toBe("true");
		}
		const free = one<HTMLInputElement>(
			root,
			"qgis-distance[name='free'] input",
		);
		expect(free.required).toBe(false);
		expect(free.hasAttribute("aria-required")).toBe(false);
	});
});

describe("JobProgress(cancellable=)", () => {
	test("cancellable=false hides the cancel button even with a cancel", async () => {
		const root = await mount(
			html`<qgis-job-progress label="Job" status="pending" .cancel=${() => undefined}></qgis-job-progress>`,
		);
		expect(root.querySelector("[data-part='cancel']")).not.toBeNull();
		const element = one<InstanceType<typeof ui.QgisJobProgress>>(
			root,
			"qgis-job-progress",
		);
		expect(element.cancellable).toBe(true);
		element.cancellable = false;
		await tick();
		expect(root.querySelector("[data-part='cancel']")).toBeNull();
	});
});

describe("Button(text=)", () => {
	test("`text` is the caption, the same property as `label`", async () => {
		const root = await mount(
			html`<qgis-run-button text="Buffer"></qgis-run-button>`,
		);
		const button = one<RunButton>(root, "qgis-run-button");
		expect(button.label).toBe("Buffer");
		expect(one<HTMLButtonElement>(root, "button").textContent).toBe("Buffer");
		button.text = "Go";
		await tick();
		expect(one<HTMLButtonElement>(root, "button").textContent).toBe("Go");
		expect(button.text).toBe("Go");
	});
});

describe("FieldPicker(of=)", () => {
	test("follows the layer picker it names, as the Python `of=` does", async () => {
		const { harness, qgis } = sdkWithHarness({
			granted: ["layers.list", "layers.get"],
		});
		expectLayers(harness, [ROADS]);
		expectLayer(harness, ROADS);
		const root = await mount(html`
			<qgis-layer-picker name="layer_id" .qgis=${qgis}></qgis-layer-picker>
			<qgis-field-picker name="field_name" .qgis=${qgis}></qgis-field-picker>
		`);
		const layers = one<LayerPicker>(root, "qgis-layer-picker");
		const fields = one<FieldPicker>(root, "qgis-field-picker");
		fields.of = layers;
		await harness.settled();
		await tick();
		expect(fields.layer).toBeNull();

		choose(one<HTMLSelectElement>(layers, "select"), ROADS.id);
		await harness.settled();
		await tick();
		expect(fields.layer).toBe(ROADS.id);
		expect(fields.options).toEqual(["name", "surface"]);

		// Detached: a later layer change is not followed.
		fields.of = null;
		layers.value = null;
		layers.dispatchEvent(
			new CustomEvent("qgis-change", {
				bubbles: true,
				detail: { name: "layer_id", value: null },
			}),
		);
		await tick();
		expect(fields.layer).toBe(ROADS.id);
		harness.assertSatisfied();
		qgis.close();
	});

	test("a picker that already has a value seeds the layer at once", async () => {
		const root = await mount(html`
			<qgis-layer-picker name="layer_id" .value=${ROADS.id}></qgis-layer-picker>
			<qgis-field-picker name="field_name" .of=${null}></qgis-field-picker>
		`);
		const fields = one<FieldPicker>(root, "qgis-field-picker");
		fields.of = one<LayerPicker>(root, "qgis-layer-picker");
		await tick();
		expect(fields.layer).toBe(ROADS.id);
	});
});
