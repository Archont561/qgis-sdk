/**
 * `dist/style.css` as the build makes it (task-70 AC #5, #6): compiled from
 * the sources, every utility `qs-` prefixed, no preflight, every colour a
 * `--qgis-sdk-*` token, inside the documented budget, and without one
 * selector in common with a consumer's own Tailwind-style utilities.
 */

import { describe, expect, test } from "bun:test";
import {
	existsSync,
	mkdtempSync,
	readFileSync,
	rmSync,
	symlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createGenerator } from "@unocss/core";
import {
	buildStyle,
	STYLE_BUDGET_BYTES,
	sourceFiles,
	writeStyle,
} from "../scripts/build-css";
import { PRESET_TOKENS, presetQgisSdk, tokenColours } from "../src/uno";

const built = await buildStyle();

/** Every selector of a stylesheet, one per rule. */
function selectors(css: string): string[] {
	return [...css.matchAll(/^([^@/\s{}][^{}\n]*)\{/gm)].map((match) =>
		(match[1] as string).trim(),
	);
}

/** Every `qs-` class the sources use, with its variant prefix. */
function classesInSources(): Set<string> {
	const used = new Set<string>();
	for (const file of sourceFiles()) {
		for (const match of readFileSync(file, "utf8").matchAll(
			/(?:[a-z-]+:)?qs-[a-z0-9-]+/g,
		)) {
			used.add(match[0]);
		}
	}
	return used;
}

describe("style.css", () => {
	test("is inside the documented budget and starts with the token defaults", () => {
		expect(Buffer.byteLength(built.style, "utf8")).toBeLessThanOrEqual(
			STYLE_BUDGET_BYTES,
		);
		expect(built.style).toContain(":root {\n  --qgis-sdk-bg:");
		expect(built.tokens).toContain('[data-qgis-sdk-theme="dark"]');
		expect(built.tokens).not.toContain(".qs-");
	});

	test("every utility the sources use is compiled, and nothing else", () => {
		const used = classesInSources();
		expect(used.size).toBeGreaterThan(30);
		const matched = new Set(built.matched);
		for (const name of used) {
			expect(matched.has(name)).toBe(true);
		}
		expect([...matched].filter((name) => !used.has(name))).toEqual([]);
	});

	test("every selector is a qs- class, :root, or the theme attribute; no preflight", () => {
		const found = selectors(built.style);
		expect(found.length).toBeGreaterThan(30);
		for (const selector of found) {
			expect(selector).toMatch(
				/^(\.(?:[a-z-]+\\:)?qs-|:root$|\[data-qgis-sdk-theme=)/,
			);
		}
		expect(built.style).not.toMatch(/^\*|^html|^body|^button|^input/m);
	});

	test("every colour declaration reads a --qgis-sdk-* token", () => {
		const utilities = built.style.slice(built.style.indexOf("/* layer"));
		for (const match of utilities.matchAll(
			/(color|background-color|border-color|outline-color|accent-color):([^;]+);/g,
		)) {
			expect(match[2]).toMatch(/^var\(--qgis-sdk-[a-z-]+\)$/);
		}
		expect(utilities).not.toMatch(/#[0-9a-f]{3,8}\b/i);
		expect(utilities).toContain("border-radius:var(--qgis-sdk-radius)");
	});

	test("shares no selector with a consumer's unprefixed utilities, preflight included", () => {
		// Their build runs in its own process: see tests/support/consumer-css.ts.
		const run = Bun.spawnSync([
			process.execPath,
			join(import.meta.dir, "support", "consumer-css.ts"),
		]);
		expect(run.exitCode).toBe(0);
		const theirs = run.stdout.toString();
		const theirSelectors = new Set(selectors(theirs));
		expect(theirSelectors.has(".flex")).toBe(true);
		expect(theirSelectors.has(".disabled\\:opacity-60:disabled")).toBe(true);
		expect(theirs).toContain("*,::before,::after");
		for (const selector of selectors(built.style)) {
			if (selector === ":root") {
				continue;
			}
			expect(theirSelectors.has(selector)).toBe(false);
		}
		// Their `--un-*` defaults are not ours either.
		expect(built.style).not.toContain("--un-");
	});
});

describe("the build script", () => {
	test("writes both stylesheets under dist/ and refuses a style.css over budget", async () => {
		const root = mkdtempSync(join(tmpdir(), "qgis-sdk-ui-"));
		try {
			symlinkSync(join(import.meta.dir, "..", "src"), join(root, "src"));
			const written = await writeStyle(root);
			expect(readFileSync(join(root, "dist", "style.css"), "utf8")).toBe(
				written.style,
			);
			expect(readFileSync(join(root, "dist", "tokens.css"), "utf8")).toBe(
				written.tokens,
			);
			await expect(writeStyle(root, 100)).rejects.toThrow(
				/over the 100-byte budget/,
			);
		} finally {
			rmSync(root, { recursive: true, force: true });
		}
		expect(existsSync(root)).toBe(false);
	});
});

describe("the /uno preset", () => {
	test("binds the colours to the tokens, prefixes, and leaves preflight out", async () => {
		const colours = tokenColours();
		expect(colours.surface).toBe("var(--qgis-sdk-surface)");
		expect(PRESET_TOKENS).toContain("radius");
		const generator = await createGenerator({ presets: [presetQgisSdk()] });
		const result = await generator.generate(
			"qs-bg-surface qs-rounded qs-accent-accent qs-accent-nope bg-surface",
			{
				preflights: true,
			},
		);
		expect(result.css).toContain(
			".qs-bg-surface{background-color:var(--qgis-sdk-surface);}",
		);
		expect(result.css).toContain(
			".qs-rounded{border-radius:var(--qgis-sdk-radius);}",
		);
		expect(result.css).toContain(
			".qs-accent-accent{accent-color:var(--qgis-sdk-accent);}",
		);
		expect(result.css).not.toContain("accent-nope");
		expect(result.css).not.toContain(".bg-surface");
		expect(result.css).not.toContain("*,::before,::after");
	});
});
