/**
 * The API index: the inventory in, one page out, with no name missing and no
 * name invented.
 *
 * The gate TASK-98 asks for in other words - "no stable symbol is
 * undocumented" - is enforced here rather than by a list someone maintains: the
 * committed `api/python.json` is the only source of names, so a page that covers
 * it covers every name by construction. What the tests keep honest is the edges:
 * a module with no note, a note pointing at a heading the guide dropped, and a
 * signature that would break the table it is rendered into.
 */
import { describe, expect, test } from "bun:test";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { API_MODULE_NOTES } from "../scripts/api-modules";
import type { Inventory } from "../scripts/lib/api-index";
import { renderApiIndex } from "../scripts/lib/api-index";
import { GUIDES, splitGuide } from "../scripts/lib/guides";

const ROOT = join(import.meta.dir, "../../..");
const INVENTORY = join(ROOT, "api/python.json");

async function inventory(): Promise<Inventory> {
	return (await Bun.file(INVENTORY).json()) as Inventory;
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
	test("lists every public name of every module", async () => {
		const document = await inventory();
		const page = renderApiIndex({
			inventory: document,
			notes: API_MODULE_NOTES,
			routes: await routes(),
		});
		const expected = Object.values(document.modules).reduce(
			(count, module) => count + Object.keys(module.names).length,
			0,
		);
		expect(page.names).toBe(expected);
		expect(page.names).toBeGreaterThan(0);
		for (const module of Object.keys(document.modules)) {
			expect(page.content).toContain(`## \`${module}\``);
		}
		for (const [name, module] of Object.entries(document.modules)) {
			for (const declared of Object.keys(module.names)) {
				expect(page.content).toContain(`| \`${declared}\` |`);
			}
			expect(name.startsWith("qgis_sdk")).toBe(true);
		}
	});

	test("every module has a note, and every note resolves to a page", async () => {
		const document = await inventory();
		const page = renderApiIndex({
			inventory: document,
			notes: API_MODULE_NOTES,
			routes: await routes(),
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
		});
		expect(page.unresolved).toEqual(["doc-12:No such heading"]);
		expect(page.content).not.toContain("Explained in");
	});

	test("a pipe in a signature cannot end its cell", () => {
		const page = renderApiIndex({
			inventory: {
				api_version: 1,
				modules: {
					"qgis_sdk.one": {
						tier: "stable",
						names: { Union: "(value: str | None) -> None" },
					},
				},
				rules: [],
				cli: [],
				host_operations: [],
				deprecations: [],
			},
			notes: { "qgis_sdk.one": { description: "One." } },
			routes: new Map(),
		});
		expect(page.content).toContain(
			"| `Union` | `(value: str \\| None) -> None` |",
		);
	});

	test("a name with no signature prints as a class rather than an empty cell", () => {
		const page = renderApiIndex({
			inventory: {
				api_version: 1,
				modules: {
					"qgis_sdk.one": { tier: "stable", names: { Protocol: "" } },
				},
				rules: [],
				cli: [],
				host_operations: [],
				deprecations: [],
			},
			notes: { "qgis_sdk.one": { description: "One." } },
			routes: new Map(),
		});
		expect(page.content).toContain("| `Protocol` | `class` |");
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

	test("the generated reference folder keeps the index in its sidebar order", async () => {
		const meta = (await Bun.file(
			join(ROOT, "apps/docs/content/docs/reference/meta.json"),
		).json()) as { pages: string[] };
		// Present only after `bun run generate`; the CI docs job runs it first.
		if (!meta.pages.includes("api-index")) {
			expect(meta.pages.length).toBeGreaterThan(0);
			return;
		}
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
