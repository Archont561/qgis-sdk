/**
 * `qgis-form` over a `FormStore`: one control per declared field in
 * declaration order, the catalogue's elements for the kinds that have one,
 * changes written to the store, errors next to their field once submitted,
 * and the focus order following the declaration (task-70 AC #1, #7).
 */

import { afterAll, describe, expect, test } from "bun:test";
import { formStore } from "@archont561/qgis-sdk";
import { fault } from "@archont561/qgis-sdk/testing";
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
const { choose, mount, one, type, ui } = await import("./support/elements");

type Form = InstanceType<typeof ui.QgisForm>;

const FOCUSABLE =
	"input:not([type=hidden]), select, button, [tabindex]:not([tabindex='-1'])";

describe("qgis-form", () => {
	test("renders every field in declaration order with the catalogue's elements", async () => {
		const { harness, qgis } = sdkWithHarness();
		expectLayers(harness);
		const form = formStore(qgis, "buffer");
		const root = await mount(
			html`<qgis-form label="Buffer" .store=${form} .qgis=${qgis}></qgis-form>`,
		);
		await harness.settled();
		await tick();

		const fields = [...root.querySelectorAll<HTMLElement>("[data-field]")];
		expect(fields.map((field) => field.dataset.field)).toEqual(
			form.fields.map((f) => f.name),
		);
		expect(fields.map((field) => field.firstElementChild?.localName)).toEqual([
			"qgis-layer-picker",
			"qgis-field-picker",
			"qgis-distance",
			"qgis-crs-picker",
			"qgis-choice",
			"qgis-file-input",
			"qgis-directory-input",
			"label", // note: a plain text input
			"label", // dissolve: a checkbox inside its label
			"label", // segments: a plain integer input
			"label", // colour: a plain colour input
		]);
		const plain = fields
			.slice(7)
			.map((field) => one<HTMLInputElement>(field, "input").type);
		expect(plain).toEqual(["text", "checkbox", "number", "color"]);
		expect(one<HTMLInputElement>(fields[9] as HTMLElement, "input").step).toBe(
			"1",
		);
		expect(
			one<HTMLInputElement>(fields[9] as HTMLElement, "input").required,
		).toBe(false);
		expect(one<HTMLInputElement>(fields[2] as HTMLElement, "input").min).toBe(
			"0",
		);

		// Every label points at a control in the light DOM, and the focus order
		// is the declaration order followed by the run button.
		for (const label of root.querySelectorAll<HTMLLabelElement>("label[for]")) {
			expect(root.querySelector(`#${label.htmlFor}`)).not.toBeNull();
		}
		const focusable = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)];
		const fieldOf = (element: HTMLElement): string | undefined =>
			element.closest<HTMLElement>("[data-field]")?.dataset.field;
		const order = focusable
			.map(fieldOf)
			.filter((name, index, all) => all.indexOf(name) === index);
		expect(order).toEqual([...form.fields.map((f) => f.name), undefined]);
		expect(focusable.at(-1)?.localName).toBe("button");
		expect(focusable.at(-1)?.closest("qgis-run-button")).not.toBeNull();
		expect(one<HTMLElement>(root, "form").getAttribute("aria-labelledby")).toBe(
			one<HTMLElement>(root, "h2[data-part='label']").id,
		);
		harness.assertSatisfied();
		qgis.close();
	});

	test("changes flow into the store; the field picker follows the layer", async () => {
		const { harness, qgis } = sdkWithHarness();
		expectLayers(harness);
		expectLayer(harness, ROADS);
		const form = formStore(qgis, "buffer");
		const root = await mount(
			html`<qgis-form .store=${form} .qgis=${qgis}></qgis-form>`,
		);
		await harness.settled();
		await tick();
		const field = (name: string): HTMLElement =>
			one<HTMLElement>(root, `[data-field='${name}']`);

		choose(one<HTMLSelectElement>(field("layer_id"), "select"), "roads-1");
		await harness.settled();
		await tick();
		expect(form.getSnapshot().values.layer_id).toBe("roads-1");
		expect(
			[...one<HTMLSelectElement>(field("field_name"), "select").options].map(
				(o) => o.textContent,
			),
		).toEqual(["Choose a field…", "name", "surface"]);
		choose(one<HTMLSelectElement>(field("field_name"), "select"), "name");
		type(one<HTMLInputElement>(field("distance_metres"), "input"), "12");
		type(one<HTMLInputElement>(field("crs"), "input"), "EPSG:2180");
		choose(one<HTMLSelectElement>(field("mode"), "select"), "1");
		type(one<HTMLInputElement>(field("note"), "input"), "hello");
		const dissolve = one<HTMLInputElement>(field("dissolve"), "input");
		dissolve.checked = true;
		dissolve.dispatchEvent(new Event("change", { bubbles: true }));
		type(one<HTMLInputElement>(field("segments"), "input"), "8");
		type(one<HTMLInputElement>(field("colour"), "input"), "#ff0000");
		await tick();
		expect(form.getSnapshot().values).toEqual({
			layer_id: "roads-1",
			field_name: "name",
			distance_metres: 12,
			crs: "EPSG:2180",
			mode: "exact",
			note: "hello",
			dissolve: true,
			segments: 8,
			colour: "#ff0000",
		});
		expect(form.getSnapshot().valid).toBe(true);
		type(one<HTMLInputElement>(field("note"), "input"), "");
		await tick();
		expect(form.getSnapshot().values.note).toBeNull();
		harness.assertSatisfied();
		qgis.close();
	});

	test("errors appear next to their field once submitted; a failure under the button", async () => {
		const { harness, qgis } = sdkWithHarness({ granted: [] });
		harness.expectInvoke("buffer", () => fault("internal", "host said no"));
		const form = formStore(qgis, "buffer");
		const root = await mount(
			html`<qgis-form .store=${form} .qgis=${qgis} submit-label="Run it"></qgis-form>`,
		);
		await harness.settled();
		await tick();
		expect(
			root.querySelectorAll("[data-field] [data-part='error']"),
		).toHaveLength(1);
		// The layer picker's refusal is the only message before a submit.
		expect(
			one<HTMLElement>(root, "[data-field='layer_id'] [data-part='error']")
				.textContent,
		).toContain("layers.read");
		const button = one<HTMLButtonElement>(root, "qgis-run-button button");
		expect(button.textContent).toBe("Run it");
		button.click();
		await tick();
		const errors = [
			...root.querySelectorAll<HTMLElement>("[data-field] [data-part='error']"),
		];
		expect(
			errors.map(
				(error) => error.closest<HTMLElement>("[data-field]")?.dataset.field,
			),
		).toEqual(["layer_id", "distance_metres"]);
		expect(
			one<HTMLElement>(
				root,
				"[data-field='distance_metres'] [data-part='error']",
			).textContent,
		).toBe(form.getSnapshot().errors.distance_metres);
		const control = one<HTMLInputElement>(
			root,
			"[data-field='distance_metres'] input",
		);
		expect(control.getAttribute("aria-invalid")).toBe("true");
		expect(harness.calls.map((call) => call.kind)).toEqual(["handshake"]);

		form.setValues({ layer_id: "roads-1", distance_metres: 1 });
		await harness.settled();
		await tick();
		// The validation errors are gone; the field picker, now asked for the
		// layer's fields, is refused like the layer picker.
		expect(
			[
				...root.querySelectorAll<HTMLElement>(
					"[data-field] [data-part='error']",
				),
			].map(
				(error) => error.closest<HTMLElement>("[data-field]")?.dataset.field,
			),
		).toEqual(["layer_id", "field_name"]);
		button.click();
		await harness.settled();
		await tick();
		expect(
			one<HTMLElement>(root, "form > [data-part='error']").textContent,
		).toBe("host said no");
		harness.assertSatisfied();
		qgis.close();
	});

	test("the native submit event submits through the store; a form without a store says so", async () => {
		const { harness, qgis } = sdkWithHarness();
		expectLayers(harness);
		expectLayer(harness, ROADS);
		harness.expectInvoke("buffer", () => ({ id: "ok" }));
		const form = formStore(qgis, "buffer", {
			initial: { layer_id: "roads-1", distance_metres: 1 },
		});
		const root = await mount(
			html`<qgis-form .store=${form} .qgis=${qgis}></qgis-form>`,
		);
		const results: unknown[] = [];
		root.addEventListener("qgis-result", (event) =>
			results.push((event as CustomEvent).detail),
		);
		const formElement = one<HTMLFormElement>(root, "form");
		const submit = new Event("submit", { bubbles: true, cancelable: true });
		formElement.dispatchEvent(submit);
		expect(submit.defaultPrevented).toBe(true);
		await harness.settled();
		await tick();
		expect(form.getSnapshot().submission).toEqual({
			status: "ok",
			value: { id: "ok" },
		});
		// Submitting through the form element, not the button, raises no qgis-result.
		expect(results).toEqual([]);
		const element = one<Form>(root, "qgis-form");
		expect(element.state?.submitted).toBe(true);
		element.store = null;
		await tick();
		expect(one<HTMLElement>(root, "[data-part='status']").textContent).toBe(
			"No form bound.",
		);
		harness.assertSatisfied();
		qgis.close();
	});

	test("file and directory fields take their pickers by field name; disabled reaches every control", async () => {
		const { qgis } = sdkWithHarness();
		const gpkg = { id: "r1", kind: "file" as const, name: "out.gpkg" };
		const form = formStore(qgis, "buffer");
		const root = await mount(
			html`<qgis-form .store=${form} .pickers=${{ output: async () => gpkg }} disabled></qgis-form>`,
		);
		await tick();
		for (const control of root.querySelectorAll<HTMLInputElement>(
			"input, select, button",
		)) {
			expect(control.disabled).toBe(true);
		}
		const element = one<Form>(root, "qgis-form");
		element.disabled = false;
		await tick();
		expect(
			one<HTMLButtonElement>(root, "[data-field='output'] [data-part='pick']")
				.disabled,
		).toBe(false);
		expect(
			one<HTMLButtonElement>(root, "[data-field='folder'] [data-part='pick']")
				.disabled,
		).toBe(true);
		one<HTMLButtonElement>(
			root,
			"[data-field='output'] [data-part='pick']",
		).click();
		await tick();
		expect(form.getSnapshot().values.output).toEqual(gpkg);
		expect(
			one<HTMLInputElement>(root, "[data-field='output'] input").value,
		).toBe("out.gpkg");
		qgis.close();
	});
});
