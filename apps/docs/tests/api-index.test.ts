/**
 * The API index: the inventory in, one coverage page out, with no module
 * missing and no member row.
 *
 * Since decision-86 the member documentation lives in the generated Python
 * reference (`reference/python/`), so this page keeps the coverage table -
 * every module with its tier and name count - and links each module to its
 * generated page. The gate TASK-98 asks for in other words - "no stable symbol
 * is undocumented" - is enforced at the module level by
 * `test_the_scope_is_every_module_the_inventory_publishes`, which holds the
 * fumero scope to the inventory; fumero renders every name in a module by
 * construction. What these tests keep honest is the edges: a module with no
 * note, a note pointing at a heading the guide dropped, and a description that
 * would break the table it is rendered into.
 */
import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { API_MODULE_NOTES } from "../scripts/api-modules";
import { type Inventory, renderApiIndex } from "../scripts/lib/api-index";
import { GUIDES, splitGuide } from "../scripts/lib/guides";
import { readInventory } from "../scripts/lib/inventory";

const ROOT = join(import.meta.dir, "../../..");
const INVENTORY = join(ROOT, "api/python.json");

async function inventory(): Promise<Inventory> {
	return readInventory(INVENTORY);
}

/** `guide id:heading` to the route the rendered guides put that heading on. */
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

describe("renderApiIndex", () => {
	test("covers every module with its tier and name count, and no member row", async () => {
		const document = await inventory();
		const page = renderApiIndex({
			inventory: document,
			notes: API_MODULE_NOTES,
			routes: await routes(),
			pythonReference: true,
		});
		const expected = Object.values(document.modules).reduce(
			(count, module) => count + Object.keys(module.names).length,
			0,
		);
		expect(page.names).toBe(expected);
		expect(page.names).toBeGreaterThan(0);
		for (const [name, module] of Object.entries(document.modules)) {
			const counted = Object.keys(module.names).length;
			expect(page.content).toContain(
				`| \`${name}\` | \`${module.tier}\` | ${counted} |`,
			);
			expect(name.startsWith("qgis_sdk")).toBe(true);
			// The member rows are not here: the generated Python reference
			// documents each name (decision-86).
			for (const declared of Object.keys(module.names)) {
				expect(page.content).not.toContain(`| \`${declared}\` |`);
			}
		}
	});

	test("links each module to its generated reference page", async () => {
		const document = await inventory();
		const page = renderApiIndex({
			inventory: document,
			notes: API_MODULE_NOTES,
			routes: await routes(),
			pythonReference: true,
		});
		for (const name of Object.keys(document.modules)) {
			const route = `/reference/python/${name.split(".").join("/")}/`;
			expect(page.content).toContain(`[Python reference](${route})`);
		}
	});

	test("omits the reference column when the reference was not generated", () => {
		const page = renderApiIndex({
			inventory: {
				api_version: 1,
				modules: {
					"qgis_sdk.one": { tier: "stable", names: { Thing: "() -> None" } },
				},
				rules: [],
				cli: [],
				host_operations: [],
				deprecations: [],
			},
			notes: { "qgis_sdk.one": { description: "One." } },
			routes: new Map(),
			pythonReference: false,
		});
		expect(page.content).toContain("| Module | Tier | Names | What it is |");
		expect(page.content).not.toContain("[Python reference]");
	});

	test("every module has a note, and every note resolves to a page", async () => {
		const document = await inventory();
		const page = renderApiIndex({
			inventory: document,
			notes: API_MODULE_NOTES,
			routes: await routes(),
			pythonReference: true,
		});
		expect(page.undescribed).toEqual([]);
		expect(page.unresolved).toEqual([]);
	});

	test("a module without a note is reported, not silently rendered", () => {
		const page = renderApiIndex({
			inventory: {
				api_version: 1,
				modules: {
					"qgis_sdk.unnoted": {
						tier: "stable",
						names: { Thing: "() -> None" },
					},
				},
				rules: [],
				cli: [],
				host_operations: [],
				deprecations: [],
			},
			notes: {},
			routes: new Map(),
			pythonReference: true,
		});
		expect(page.undescribed).toEqual(["qgis_sdk.unnoted"]);
	});

	test("a note whose heading the guide dropped is reported", () => {
		const page = renderApiIndex({
			inventory: {
				api_version: 1,
				modules: {
					"qgis_sdk.one": { tier: "stable", names: { Thing: "() -> None" } },
				},
				rules: [],
				cli: [],
				host_operations: [],
				deprecations: [],
			},
			notes: {
				"qgis_sdk.one": {
					description: "One.",
					section: { guide: "doc-12", heading: "No such heading" },
				},
			},
			routes: new Map(),
			pythonReference: true,
		});
		expect(page.unresolved).toEqual(["doc-12:No such heading"]);
		expect(page.content).not.toContain("Explained in");
	});

	test("a pipe in a description cannot end its cell", () => {
		const page = renderApiIndex({
			inventory: {
				api_version: 1,
				modules: {
					"qgis_sdk.one": {
						tier: "stable",
						names: { Thing: "() -> None" },
					},
				},
				rules: [],
				cli: [],
				host_operations: [],
				deprecations: [],
			},
			notes: { "qgis_sdk.one": { description: "One | two." } },
			routes: new Map(),
			pythonReference: true,
		});
		expect(page.content).toContain("One \\| two.");
		expect(page.content).not.toContain("One | two.");
	});

	test("counts the surfaces it does not list instead of naming them", () => {
		const document = {
			api_version: 1,
			modules: {},
			rules: ["R1", "R2"],
			cli: ["build"],
			host_operations: ["a.b", "c.d", "e.f"],
			deprecations: [],
		} satisfies Inventory;
		const page = renderApiIndex({
			inventory: document,
			notes: {},
			routes: new Map(),
			pythonReference: true,
		});
		expect(page.content).toContain("the 1 `qgis-sdk` commands");
		expect(page.content).toContain("the 2 check rule ids");
		expect(page.content).toContain("the 3 host operations");
	});

	test("states an empty deprecation record as empty, and lists one that is not", () => {
		const base = {
			api_version: 1,
			modules: {},
			rules: [],
			cli: [],
			host_operations: [],
			deprecations: [],
		} satisfies Inventory;
		const empty = renderApiIndex({
			inventory: base,
			notes: {},
			routes: new Map(),
			pythonReference: true,
		});
		expect(empty.content).toContain(
			"No name in this release carries a deprecation mark",
		);
		const marked = renderApiIndex({
			inventory: {
				...base,
				deprecations: [
					{
						module: "qgis_sdk.models",
						name: "OldName",
						since: "0.9.0",
						removal: "1.0.0",
						use: "NewName",
					},
				],
			},
			notes: {},
			routes: new Map(),
			pythonReference: true,
		});
		expect(marked.content).toContain(
			"`qgis_sdk.models.OldName` (deprecated since 0.9.0, removed in 1.0.0, use `NewName`)",
		);
	});
});

describe("api-modules notes", () => {
	test("describes every module that exists and nothing else", async () => {
		const document = await inventory();
		expect(Object.keys(API_MODULE_NOTES).sort()).toEqual(
			Object.keys(document.modules).sort(),
		);
	});

	test("every description ends in a full stop and names no module twice", async () => {
		for (const [name, note] of Object.entries(API_MODULE_NOTES)) {
			expect(note.description.endsWith(".")).toBe(true);
			expect(note.description.length).toBeGreaterThan(20);
			if (note.section !== undefined) {
				expect(["doc-12", "doc-13", "doc-14"]).toContain(note.section.guide);
			}
			expect(name).toBe(name.trim());
		}
	});
});

describe("the guides behind the notes", () => {
	test("every cited heading is a section of the guide it names", async () => {
		const available = await routes();
		for (const [module, note] of Object.entries(API_MODULE_NOTES)) {
			const section = note.section;
			if (section === undefined) {
				continue;
			}
			expect(available.has(`${section.guide}:${section.heading}`)).toBe(true);
			expect(module).toContain("qgis_sdk");
		}
	});

	test("the reference sidebar puts the index first when the generator has run", async () => {
		// `content/docs/` holds generated files and is ignored by git, so this
		// reads it only when `bun run generate` has run in this checkout - the
		// coverage job does not run it, and a test may not need it to exist.
		const path = join(ROOT, "apps/docs/content/docs/reference/meta.json");
		if (!existsSync(path)) {
			return;
		}
		const meta = (await Bun.file(path).json()) as { pages: string[] };
		expect(meta.pages[0]).toBe("api-index");
	});
});

describe("the reference folder", () => {
	test("holds the hand-written pages the generator must not delete", async () => {
		const entries = await readdir(
			join(ROOT, "apps/docs/content/docs/reference"),
		);
		expect(entries).toContain("faq.md");
	});
});
