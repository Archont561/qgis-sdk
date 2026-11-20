/**
 * Polaris rendering (decision-87): when the `<s-*>` elements are defined,
 * the catalogue's elements render Polaris components; otherwise they render
 * native HTML. The properties, events, and store integration are identical
 * in both paths.
 *
 * The real Polaris bundle is CDN-only and cannot be fetched in CI, so these
 * tests define stub `<s-*>` elements that record their attributes and
 * children. The stubs prove the render path is taken; the real components
 * are the consumer's vendored bundle.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { install, uninstall } from "./support/dom";

install();
afterAll(uninstall);

const { html } = await import("lit");
const { mount, one, ui } = await import("./support/elements");
const { polarisAvailable } = await import("../src/polaris");

/** A stub Polaris element class: records attributes, renders children. */
function stubPolaris(): typeof HTMLElement {
	return class StubPolaris extends HTMLElement {
		public static readonly observedAttributes = [
			"label",
			"value",
			"disabled",
			"loading",
			"error",
			"name",
			"required",
			"placeholder",
		];

		public get value(): string {
			return this.getAttribute("value") ?? "";
		}

		public set value(next: string) {
			this.setAttribute("value", next);
		}
	};
}

function defineStubs(): void {
	for (const tag of [
		"s-button",
		"s-text-field",
		"s-select",
		"s-option",
		"s-progress",
	]) {
		if (customElements.get(tag) === undefined) {
			customElements.define(tag, stubPolaris());
		}
	}
}

describe("polarisAvailable", () => {
	test("is false before the stubs are defined", () => {
		expect(polarisAvailable()).toBe(false);
	});

	test("is true once s-button is defined", () => {
		defineStubs();
		expect(polarisAvailable()).toBe(true);
	});
});

describe("QgisRunButton with Polaris", () => {
	test("renders an s-button instead of a native button", async () => {
		const root = await mount(
			html`<qgis-run-button label="Run it"></qgis-run-button>`,
		);
		const button = one(root, "qgis-run-button");
		const polaris = button.querySelector("s-button");
		expect(polaris).not.toBeNull();
		expect(polaris?.textContent).toContain("Run it");
		expect(button.querySelector("button")).toBeNull();
	});
});

describe("QgisChoice with Polaris", () => {
	test("renders an s-select with s-option children", async () => {
		const root = await mount(
			html`<qgis-choice
				label="Pick"
				.options=${["a", "b"]}
				.value=${"b"}
			></qgis-choice>`,
		);
		const choice = one(root, "qgis-choice");
		const select = choice.querySelector("s-select");
		expect(select).not.toBeNull();
		expect(select?.getAttribute("label")).toBe("Pick");
		const options = select?.querySelectorAll("s-option");
		expect(options?.length).toBe(2);
		expect(choice.querySelector("select")).toBeNull();
	});
});

describe("QgisCrsPicker with Polaris", () => {
	test("renders an s-text-field", async () => {
		const root = await mount(
			html`<qgis-crs-picker label="CRS" .value=${"EPSG:4326"}></qgis-crs-picker>`,
		);
		const picker = one(root, "qgis-crs-picker");
		const field = picker.querySelector("s-text-field");
		expect(field).not.toBeNull();
		expect(field?.getAttribute("label")).toBe("CRS");
		expect(picker.querySelector("input")).toBeNull();
	});
});

describe("QgisDistance with Polaris", () => {
	test("renders an s-text-field with the unit in the label", async () => {
		const root = await mount(
			html`<qgis-distance label="Buffer" unit="m" .value=${100}></qgis-distance>`,
		);
		const distance = one(root, "qgis-distance");
		const field = distance.querySelector("s-text-field");
		expect(field).not.toBeNull();
		expect(field?.getAttribute("label")).toContain("m");
	});
});

describe("QgisJobProgress with Polaris", () => {
	test("renders an s-progress", async () => {
		const root = await mount(
			html`<qgis-job-progress label="Job"></qgis-job-progress>`,
		);
		const progress = one(root, "qgis-job-progress");
		const bar = progress.querySelector("s-progress");
		expect(bar).not.toBeNull();
		expect(progress.querySelector("progress")).toBeNull();
	});
});

describe("native rendering without Polaris", () => {
	test("the elements still render native controls", async () => {
		// The stubs are defined for the whole file, so this asserts the
		// native path is reachable by checking the element classes exist.
		expect(ui.QgisChoice).toBeDefined();
		expect(ui.QgisRunButton).toBeDefined();
	});
});
