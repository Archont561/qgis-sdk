/**
 * The catalogue as a whole: the decision-55 tag names, idempotent
 * registration, and the one-import side-effect entry.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { install, uninstall } from "./support/dom";

install();
afterAll(uninstall);

const ui = await import("../src/index");

describe("defineElements", () => {
	test("registers the catalogue once and leaves a taken tag alone", () => {
		expect(ui.TAG_NAMES).toEqual([
			"qgis-form",
			"qgis-layer-picker",
			"qgis-crs-picker",
			"qgis-field-picker",
			"qgis-job-progress",
			"qgis-file-input",
			"qgis-directory-input",
			"qgis-distance",
			"qgis-choice",
			"qgis-log-view",
			"qgis-run-button",
		]);
		const taken = new Set<string>(["qgis-choice"]);
		const defined = new Map<string, CustomElementConstructor>();
		const registry = {
			get: (tag: string) => (taken.has(tag) ? class {} : defined.get(tag)),
			define: (tag: string, element: CustomElementConstructor) => {
				defined.set(tag, element);
			},
		} as unknown as CustomElementRegistry;
		const first = ui.defineElements(registry);
		expect(first).toEqual(ui.TAG_NAMES.filter((tag) => tag !== "qgis-choice"));
		expect(ui.defineElements(registry)).toEqual([]);
		expect(defined.get("qgis-form")).toBe(ui.QgisForm);
	});

	test("the define entry registers on the global registry, and again is a no-op", async () => {
		await import("../src/define");
		expect(customElements.get("qgis-form")).toBe(ui.QgisForm);
		expect(ui.defineElements()).toEqual([]);
		for (const tag of ui.TAG_NAMES) {
			expect(customElements.get(tag)).toBe(ui.ELEMENTS[tag]);
		}
	});

	test("every element is a light-DOM Lit element with the base's parts contract", () => {
		for (const [tag, Element] of Object.entries(ui.ELEMENTS)) {
			const element = new Element();
			expect(element).toBeInstanceOf(ui.QgisSdkElement);
			expect((Element as unknown as { tagName: string }).tagName).toBe(tag);
		}
	});
});
