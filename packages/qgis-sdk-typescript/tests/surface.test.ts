/**
 * The package's entry points stay framework-neutral (TASK-18 AC #1,
 * decision-18, TASK-69 AC #2): the root - stores included - `./bridge` and
 * `./host` load no framework, no test utility and touch no browser global.
 * `./react`, `./vue` and `./svelte` each depend on their one framework and
 * on nothing of each other, only `./testing` is a harness, and all four are
 * optional entry points.
 *
 * One module of the root reads a browser global by design: `webchannel.ts`
 * is the default transport (decision-44), and it reads `window.qt` only when
 * `createWebChannelTransport` is called, never at import.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@archont561/bun-test-utils";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const PACKAGE = join(SRC, "..", "package.json");

const NEUTRAL = [
	"index.ts",
	"bridge.ts",
	"host.ts",
	"generated/host.ts",
	"declarations.ts",
	"errors.ts",
	"internal.ts",
	"qgis-sdk.ts",
	"schema.ts",
	"stores.ts",
	"validate.ts",
	"webchannel.ts",
];
/** Each adapter, the framework it may import, and the ones it may not. */
const ADAPTERS: Record<
	string,
	{ readonly peer: RegExp; readonly others: RegExp }
> = {
	"react.ts": { peer: /^react$/, others: /^(vue|svelte)(\/|$)/ },
	"vue.ts": { peer: /^vue$/, others: /^(react|svelte)(\/|$)/ },
	"svelte.ts": { peer: /^svelte(\/store)?$/, others: /^(react|vue)(\/|$)/ },
};
/** The default transport is allowed to read `window.qt` when called. */
const TOUCHES_QT_ON_CALL = new Set(["webchannel.ts"]);
const BROWSER_GLOBALS = /\b(window|document|navigator|localStorage|qt)\s*[.[]/;
const IMPORT = /^\s*(?:import|export)\b[^;]*?\bfrom\s+["']([^"']+)["']/gm;

function importsOf(file: string): string[] {
	const text = readFileSync(join(SRC, file), "utf8");
	return [...text.matchAll(IMPORT)].map((match) => match[1] as string);
}

test("the neutral entry points import nothing outside themselves", () => {
	for (const file of NEUTRAL) {
		for (const specifier of importsOf(file)) {
			expect(specifier, `${file} imports ${specifier}`).toMatch(/^\.\.?\//);
			expect(specifier, `${file} imports ${specifier}`).not.toMatch(
				/\/(react|vue|svelte|testing)$/,
			);
		}
	}
});

test("the neutral entry points reference no browser global", () => {
	for (const file of NEUTRAL) {
		if (TOUCHES_QT_ON_CALL.has(file)) {
			continue;
		}
		const text = readFileSync(join(SRC, file), "utf8");
		const code = text.replace(/\/\*[\s\S]*?\*\//g, "");
		expect(code, file).not.toMatch(BROWSER_GLOBALS);
	}
});

test("the default transport reads the Qt global inside functions only", () => {
	const text = readFileSync(join(SRC, "webchannel.ts"), "utf8");
	const code = text.replace(/\/\*[\s\S]*?\*\//g, "");
	// Every mention of the page scope sits inside a function body (indented),
	// so importing the module evaluates none of them.
	const topLevel = code
		.split("\n")
		.filter((line) => /\b(globalThis|window)\b/.test(line))
		.filter((line) => !line.startsWith("\t"));
	expect(topLevel).toEqual([]);
	expect(code).toMatch(/globalThis/);
});

test("bundling the neutral entry points pulls in no React and no harness", async () => {
	const built = await Bun.build({
		entrypoints: NEUTRAL.slice(0, 3).map((file) => join(SRC, file)),
		target: "browser",
		minify: false,
	});
	expect(built.success).toBe(true);
	for (const artifact of built.outputs) {
		const code = await artifact.text();
		expect(code, artifact.path).not.toMatch(/react/i);
		expect(code, artifact.path).not.toMatch(/from\s+["'](vue|svelte)/);
		expect(code, artifact.path).not.toMatch(/createBridgeHarness/);
	}
});

test("bundling one adapter pulls in its own framework only", async () => {
	for (const [file, { peer, others }] of Object.entries(ADAPTERS)) {
		const built = await Bun.build({
			entrypoints: [join(SRC, file)],
			target: "browser",
			minify: false,
			external: ["react", "vue", "svelte", "svelte/store"],
		});
		expect(built.success, file).toBe(true);
		for (const artifact of built.outputs) {
			const code = await artifact.text();
			const imported = [...code.matchAll(IMPORT)].map((m) => m[1] as string);
			expect(
				imported.some((s) => peer.test(s)),
				`${file}: ${imported}`,
			).toBe(true);
			expect(
				imported.filter((s) => others.test(s)),
				file,
			).toEqual([]);
			expect(code, file).not.toMatch(/createBridgeHarness/);
		}
	}
});

test("react, vue and svelte are optional peers, and the four optional entry points are exported", () => {
	const manifest = JSON.parse(readFileSync(PACKAGE, "utf8")) as {
		readonly exports: Record<string, unknown>;
		readonly dependencies?: Record<string, string>;
		readonly peerDependencies?: Record<string, string>;
		readonly peerDependenciesMeta?: Record<string, { optional?: boolean }>;
	};
	expect(Object.keys(manifest.exports)).toEqual([
		".",
		"./bridge",
		"./host",
		"./react",
		"./vue",
		"./svelte",
		"./testing",
	]);
	expect(manifest.dependencies ?? {}).toEqual({});
	for (const peer of ["react", "vue", "svelte"]) {
		expect(manifest.peerDependencies?.[peer], peer).toBeDefined();
		expect(manifest.peerDependenciesMeta?.[peer]?.optional, peer).toBe(true);
	}
});

test("each adapter imports its own framework only, and only ./testing is a harness", () => {
	for (const [file, { peer, others }] of Object.entries(ADAPTERS)) {
		const imports = importsOf(file);
		expect(
			imports.some((s) => peer.test(s)),
			file,
		).toBe(true);
		expect(
			imports.filter((s) => others.test(s)),
			file,
		).toEqual([]);
		expect(imports, file).not.toContain("./testing");
		expect(imports, file).toContain("./stores");
	}
	for (const peer of ["react", "vue", "svelte"]) {
		expect(importsOf("testing.ts")).not.toContain(peer);
	}
	for (const file of [...Object.keys(ADAPTERS), "testing.ts"]) {
		const text = readFileSync(join(SRC, file), "utf8");
		expect(text, file).not.toMatch(BROWSER_GLOBALS);
	}
});
