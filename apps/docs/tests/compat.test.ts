/**
 * The landing page's one compatibility sentence is read from the support
 * matrix, so the parser is what keeps it true: qualified rows only, newest
 * series first, and the LTS label taken from the row that says it.
 */
import { describe, expect, test } from "bun:test";
import { collectCompat } from "../scripts/lib/compat";

const MATRIX = [
	"<!-- support-matrix:begin -->",
	"| OS | Arch | Python | QGIS | Qt | Chromium | Status | Evidence |",
	"| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |",
	"| linux | x86-64 | 3.14 | 4.2 | 6.11 | 140 | qualified | the locked environment |",
	"| linux | x86-64 | 3.12 | 3.44 | 5.15 | - | qualified | ci.yml `QGIS 3.44 LTS` |",
	"| linux | x86-64 | 3.11 | - | - | - | qualified | the QGIS-free suite |",
	"| windows | x86-64 | 3.14 | 4.2 | - | - | unqualified | no Windows QGIS 4 |",
	"<!-- support-matrix:end -->",
].join("\n");

describe("collectCompat", () => {
	test("counts only qualified rows and reads the QGIS series newest first", () => {
		const compat = collectCompat(MATRIX);
		expect(compat.qgis).toEqual([
			{ series: "4.2", lts: false },
			{ series: "3.44", lts: true },
		]);
		expect(compat.qualified).toBe(3);
	});

	test("the Python range spans the qualified rows, not the manifest floor", () => {
		expect(collectCompat(MATRIX).python).toEqual({ min: "3.11", max: "3.14" });
	});

	test("a guide with no matrix answers with nothing rather than with a claim", () => {
		const compat = collectCompat("# A guide with no table\n");
		expect(compat.qgis).toEqual([]);
		expect(compat.qualified).toBe(0);
	});
});
