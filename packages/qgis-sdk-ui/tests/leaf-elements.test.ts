/**
 * The leaf controls without a host behind them: choice, distance, CRS, file
 * and directory inputs. Each renders in the light DOM with its label wired
 * to its control, reports `qgis-change` with a typed value, and shows an
 * error under the control (task-70 AC #5, #7).
 */

import { afterAll, describe, expect, test } from "bun:test";
import { install, tick, uninstall } from "./support/dom";

install();
afterAll(uninstall);

const { html } = await import("lit");
const { choose, mount, one, type, ui } = await import("./support/elements");

function changes(root: HTMLElement): unknown[] {
	const seen: unknown[] = [];
	root.addEventListener("qgis-change", (event) => {
		seen.push((event as CustomEvent).detail);
	});
	return seen;
}

describe("light DOM and parts", () => {
	test("every element renders into itself, stamped data-qgis-sdk, label for control", async () => {
		const root = await mount(html`
			<qgis-choice name="mode" label="Mode" .choices=${["fast"]}></qgis-choice>
			<qgis-distance name="d" label="Distance"></qgis-distance>
			<qgis-crs-picker name="crs" label="CRS"></qgis-crs-picker>
			<qgis-file-input name="out" label="Output"></qgis-file-input>
			<qgis-directory-input name="dir" label="Folder"></qgis-directory-input>
			<qgis-log-view></qgis-log-view>
		`);
		for (const element of root.querySelectorAll("[data-qgis-sdk]")) {
			expect(element.shadowRoot).toBeNull();
			const label = element.querySelector<HTMLLabelElement>(
				"[data-part='label']",
			);
			const control = one<HTMLElement>(element, "[data-part='control']");
			if (label !== null && label.tagName === "LABEL") {
				expect(label.htmlFor).toBe(control.id);
				expect(root.querySelector(`#${control.id}`)).toBe(control);
			}
		}
		expect(
			[...root.querySelectorAll("[data-qgis-sdk]")].map(
				(element) => (element as HTMLElement).dataset.qgisSdk,
			),
		).toEqual(["mode", "d", "crs", "out", "dir", "qgis-log-view"]);
	});

	test("an error renders as data-part=error, described by the control", async () => {
		const root = await mount(
			html`<qgis-distance name="d" label="Distance" error="too small"></qgis-distance>`,
		);
		const control = one<HTMLInputElement>(root, "[data-part='control']");
		const error = one<HTMLElement>(root, "[data-part='error']");
		expect(error.textContent).toBe("too small");
		expect(error.getAttribute("role")).toBe("alert");
		expect(control.getAttribute("aria-invalid")).toBe("true");
		expect(control.getAttribute("aria-describedby")).toBe(error.id);
	});
});

describe("qgis-choice", () => {
	test("reports the chosen value with its own type, null for the empty option", async () => {
		const root = await mount(
			html`<qgis-choice name="n" label="Count" nullable .choices=${[1, 2, { value: true, label: "yes" }]}></qgis-choice>`,
		);
		const seen = changes(root);
		const select = one<HTMLSelectElement>(root, "select");
		expect([...select.options].map((option) => option.textContent)).toEqual([
			"Choose…",
			"1",
			"2",
			"yes",
		]);
		choose(select, "1");
		choose(select, "2");
		choose(select, "");
		expect(seen).toEqual([
			{ name: "n", value: 2 },
			{ name: "n", value: true },
			{ name: "n", value: null },
		]);
	});

	test("a value set from outside selects its option", async () => {
		const root = await mount(
			html`<qgis-choice name="m" .choices=${["fast", "exact"]} .value=${"exact"}></qgis-choice>`,
		);
		const select = one<HTMLSelectElement>(root, "select");
		expect(one<HTMLOptionElement>(select, "option[selected]").textContent).toBe(
			"exact",
		);
		const element = one<InstanceType<typeof ui.QgisChoice>>(
			root,
			"qgis-choice",
		);
		element.value = "nowhere";
		await tick();
		expect(select.querySelectorAll("option")).toHaveLength(3);
		expect(one<HTMLOptionElement>(select, "option[selected]").value).toBe("");
	});
});

describe("qgis-distance", () => {
	test("reports a number, null when cleared or not a number", async () => {
		const root = await mount(
			html`<qgis-distance name="d" label="Distance" unit="km"></qgis-distance>`,
		);
		const seen = changes(root);
		const input = one<HTMLInputElement>(root, "input");
		expect(input.type).toBe("number");
		expect(input.min).toBe("0");
		expect(one<HTMLElement>(root, "[data-part='unit']").textContent).toBe("km");
		type(input, "12.5");
		type(input, "");
		type(input, "abc");
		expect(seen).toEqual([
			{ name: "d", value: 12.5 },
			{ name: "d", value: null },
			{ name: "d", value: null },
		]);
	});
});

describe("qgis-crs-picker", () => {
	test("offers suggestions, reports the text, flags a shape that is not AUTHORITY:CODE", async () => {
		const root = await mount(
			html`<qgis-crs-picker name="crs" label="CRS"></qgis-crs-picker>`,
		);
		const seen = changes(root);
		const input = one<HTMLInputElement>(root, "input");
		const list = one<HTMLDataListElement>(root, "datalist");
		expect(input.getAttribute("list")).toBe(list.id);
		expect(list.querySelectorAll("option").length).toBe(ui.COMMON_CRS.length);
		expect(root.querySelector("[data-part='error']")).toBeNull();

		type(input, "EPSG:2180");
		await tick();
		expect(root.querySelector("[data-part='error']")).toBeNull();
		type(input, "WGS84");
		await tick();
		expect(one<HTMLElement>(root, "[data-part='error']").textContent).toContain(
			"EPSG:4326",
		);
		expect(input.getAttribute("aria-invalid")).toBe("true");
		type(input, "");
		await tick();
		expect(root.querySelector("[data-part='error']")).toBeNull();
		expect(seen).toEqual([
			{ name: "crs", value: "EPSG:2180" },
			{ name: "crs", value: "WGS84" },
			{ name: "crs", value: null },
		]);
	});

	test("a form's own error wins over the shape message", async () => {
		const root = await mount(
			html`<qgis-crs-picker name="crs" .value=${"nope"} error="required"></qgis-crs-picker>`,
		);
		expect(one<HTMLElement>(root, "[data-part='error']").textContent).toBe(
			"required",
		);
	});
});

describe("qgis-file-input and qgis-directory-input", () => {
	const gpkg = { id: "ref-1", kind: "file" as const, name: "out.gpkg" };
	const folder = { id: "ref-2", kind: "directory" as const };

	test("without a picker the button is disabled and says why", async () => {
		const root = await mount(
			html`<qgis-file-input name="out" label="Output"></qgis-file-input>`,
		);
		const pick = one<HTMLButtonElement>(root, "[data-part='pick']");
		expect(pick.disabled).toBe(true);
		expect(pick.title).toContain("no file picker");
		expect(one<HTMLInputElement>(root, "input").readOnly).toBe(true);
		expect(one<HTMLButtonElement>(root, "[data-part='clear']").disabled).toBe(
			true,
		);
	});

	test("a picker's reference is shown by name and reported; clear reports null", async () => {
		const root = await mount(
			html`<qgis-file-input name="out" label="Output" .pick=${async () => gpkg} .filters=${["*.gpkg"]}></qgis-file-input>`,
		);
		const seen = changes(root);
		const pick = one<HTMLButtonElement>(root, "[data-part='pick']");
		expect(pick.title).toBe("*.gpkg");
		pick.click();
		await tick();
		expect(one<HTMLInputElement>(root, "input").value).toBe("out.gpkg");
		one<HTMLButtonElement>(root, "[data-part='clear']").click();
		await tick();
		expect(one<HTMLInputElement>(root, "input").value).toBe("");
		expect(seen).toEqual([
			{ name: "out", value: gpkg },
			{ name: "out", value: null },
		]);
	});

	test("a picker that returns nothing changes nothing; a wrong kind is an error", async () => {
		const root = await mount(
			html`<qgis-directory-input name="dir" label="Folder" .pick=${async () => null}></qgis-directory-input>`,
		);
		const seen = changes(root);
		const element = one<InstanceType<typeof ui.QgisDirectoryInput>>(
			root,
			"qgis-directory-input",
		);
		one<HTMLButtonElement>(root, "[data-part='pick']").click();
		await tick();
		expect(seen).toEqual([]);
		element.pick = async () => gpkg;
		await tick();
		one<HTMLButtonElement>(root, "[data-part='pick']").click();
		await tick();
		expect(one<HTMLElement>(root, "[data-part='error']").textContent).toContain(
			"Expected a directory",
		);
		element.pick = async () => folder;
		await tick();
		one<HTMLButtonElement>(root, "[data-part='pick']").click();
		await tick();
		expect(root.querySelector("[data-part='error']")).toBeNull();
		expect(one<HTMLInputElement>(root, "input").value).toBe("ref-2");
		expect(seen).toEqual([{ name: "dir", value: folder }]);
	});
});
