/**
 * The kind map: every guide-derived page declares the need it serves.
 *
 * Decision-86 item 1 scopes each page by one reader need. The generator looks
 * every page up in `PAGE_KINDS` and fails on one it does not know, so a new
 * section cannot ship without a declared kind; these tests hold the map to
 * the guides, so a renamed section fails the suite rather than the build.
 */
import { describe, expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { GUIDES, splitGuide } from "../scripts/lib/guides";
import { isKind, KIND_BUDGETS, kindOf, PAGE_KINDS } from "../scripts/lib/kinds";

const ROOT = join(import.meta.dir, "../../..");

describe("PAGE_KINDS", () => {
	test("the four kinds carry the decision-86 budgets", () => {
		expect(KIND_BUDGETS).toEqual({
			tutorial: 1200,
			"how-to": 700,
			reference: 400,
			explanation: 1500,
		});
	});

	test("every value is a kind", () => {
		for (const kind of Object.values(PAGE_KINDS)) {
			expect(isKind(kind)).toBe(true);
		}
	});

	test("every guide-derived page has a kind", async () => {
		for (const guide of GUIDES) {
			const markdown = await readFile(
				join(ROOT, "apps/docs/guides", guide.file),
				"utf8",
			);
			const split = splitGuide(markdown);
			expect(kindOf(`${guide.section}/index`)).toBeDefined();
			for (const section of split.sections) {
				expect(kindOf(`${guide.section}/${section.slug}`)).toBeDefined();
			}
		}
	});

	test("no kind is recorded for a page the guides do not produce", async () => {
		const produced = new Set<string>();
		for (const guide of GUIDES) {
			const markdown = await readFile(
				join(ROOT, "apps/docs/guides", guide.file),
				"utf8",
			);
			produced.add(`${guide.section}/index`);
			for (const section of splitGuide(markdown).sections) {
				produced.add(`${guide.section}/${section.slug}`);
			}
		}
		for (const path of Object.keys(PAGE_KINDS)) {
			expect(produced.has(path)).toBe(true);
		}
	});

	test("kindOf names the page it does not know", () => {
		expect(() => kindOf("python/no-such-page")).toThrow(
			"python/no-such-page: no kind",
		);
	});
});
