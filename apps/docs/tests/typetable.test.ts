/**
 * TypeTable content from the inventory (TASK-170 AC 7).
 *
 * The rows are rendered from the committed `api/python.json`, reusing the
 * module note map, so a stable name cannot lose its row: the generation is
 * complete by construction, and these tests hold it to the inventory. A name
 * that leaves the inventory leaves the table; a name that joins it cannot be
 * missing from the table.
 */
import { describe, expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { API_MODULE_NOTES } from "../scripts/api-modules";
import type { Inventory } from "../scripts/lib/api-index";
import { GUIDES, splitGuide } from "../scripts/lib/guides";
import { readInventory } from "../scripts/lib/inventory";
import {
	renderTypeTable,
	stableNames,
	typeTableData,
} from "../scripts/lib/typetable";

const ROOT = join(import.meta.dir, "../../..");
const INVENTORY = join(ROOT, "api/python.json");

async function inventory(): Promise<Inventory> {
	return readInventory(INVENTORY);
}

async function routes(): Promise<Map<string, string>> {
	const map = new Map<string, string>();
	for (const guide of GUIDES) {
		const markdown = await readFile(
			join(ROOT, "apps/docs/guides", guide.file),
			"utf8",
		);
		for (const section of splitGuide(markdown).sections) {
			map.set(
				`${guide.id}:${section.heading}`,
				`/${guide.section}/${section.slug}`,
			);
		}
	}
	return map;
}

describe("typeTableData", () => {
	test("every public name of a module becomes a row", async () => {
		const document = await inventory();
		const input = {
			inventory: document,
			notes: API_MODULE_NOTES,
			routes: await routes(),
		};
		for (const [module, found] of Object.entries(document.modules)) {
			const data = typeTableData(input, module);
			expect(Object.keys(data).sort()).toEqual(Object.keys(found.names).sort());
		}
	});

	test("a name with no signature prints as a class", () => {
		const data = typeTableData(
			{
				inventory: {
					api_version: 1,
					modules: {
						"qgis_sdk.one": {
							tier: "stable",
							names: { Protocol: "", Thing: "(x: int) -> None" },
						},
					},
					rules: [],
					cli: [],
					host_operations: [],
					deprecations: [],
				},
				notes: {},
				routes: new Map(),
			},
			"qgis_sdk.one",
		);
		expect(data.Protocol?.type).toBe("class");
		expect(data.Thing?.type).toBe("(x: int) -> None");
	});

	test("the description carries the tier and the guide section", async () => {
		const document = await inventory();
		const data = typeTableData(
			{
				inventory: document,
				notes: API_MODULE_NOTES,
				routes: await routes(),
			},
			"qgis_sdk.ui",
		);
		const first = Object.values(data)[0];
		expect(first?.description).toContain("Tier `stable`");
		expect(first?.typeDescriptionLink).toBeDefined();
	});

	test("an unknown module is an error, not an empty table", async () => {
		const document = await inventory();
		const input = {
			inventory: document,
			notes: API_MODULE_NOTES,
			routes: await routes(),
		};
		expect(() => typeTableData(input, "qgis_sdk.nope")).toThrow(
			"qgis_sdk.nope is not in the inventory",
		);
	});
});

describe("renderTypeTable", () => {
	test("renders a TypeTable with the data inline", async () => {
		const jsx = renderTypeTable(
			{
				inventory: {
					api_version: 1,
					modules: {
						"qgis_sdk.one": {
							tier: "stable",
							names: { Thing: "(x: int) -> None" },
						},
					},
					rules: [],
					cli: [],
					host_operations: [],
					deprecations: [],
				},
				notes: {},
				routes: new Map(),
			},
			"qgis_sdk.one",
		);
		expect(jsx).toContain("<TypeTable type={{");
		expect(jsx).toContain('"Thing"');
		expect(jsx).toContain('type: "(x: int) -> None"');
		expect(jsx).not.toContain("typeDescriptionLink");
	});

	test("renders the guide section link when the module has one", async () => {
		const jsx = renderTypeTable(
			{
				inventory: {
					api_version: 1,
					modules: {
						"qgis_sdk.one": {
							tier: "stable",
							names: { Thing: "(x: int) -> None" },
						},
					},
					rules: [],
					cli: [],
					host_operations: [],
					deprecations: [],
				},
				notes: {
					"qgis_sdk.one": {
						description: "One module.",
						section: { guide: "doc-12", heading: "Forms" },
					},
				},
				routes: new Map([["doc-12:Forms", "/python/forms"]]),
			},
			"qgis_sdk.one",
		);
		expect(jsx).toContain('typeDescriptionLink: "/python/forms/"');
	});
});

describe("completeness", () => {
	test("every stable name in the inventory has a row", async () => {
		const document = await inventory();
		const input = {
			inventory: document,
			notes: API_MODULE_NOTES,
			routes: await routes(),
		};
		const covered = new Set<string>();
		for (const module of Object.keys(document.modules)) {
			for (const name of Object.keys(typeTableData(input, module))) {
				covered.add(`${module}.${name}`);
			}
		}
		for (const name of stableNames(document)) {
			expect(covered.has(name)).toBe(true);
		}
	});

	test("stableNames lists only stable-tier names", async () => {
		const document = await inventory();
		const names = stableNames(document);
		expect(names.length).toBeGreaterThan(0);
		for (const name of names) {
			const module = name.slice(0, name.lastIndexOf("."));
			expect(document.modules[module]?.tier).toBe("stable");
		}
	});
});
