/**
 * The package's entry points stay framework-neutral (TASK-18 AC #1,
 * decision-18): the root, `./bridge` and `./host` load no React, no test
 * utility and touch no browser global. Only `./react` depends on React and
 * only `./testing` is a harness, and both are optional entry points.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@archont561/bun-test-utils";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const PACKAGE = join(SRC, "..", "package.json");

const NEUTRAL = ["index.ts", "bridge.ts", "host.ts", "generated/host.ts"];
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
				/\/(react|testing)$/,
			);
		}
	}
});

test("the neutral entry points reference no browser global", () => {
	for (const file of NEUTRAL) {
		const text = readFileSync(join(SRC, file), "utf8");
		expect(text, file).not.toMatch(BROWSER_GLOBALS);
	}
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
		expect(code, artifact.path).not.toMatch(/createBridgeHarness/);
	}
});

test("react is an optional peer, and the two optional entry points are exported", () => {
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
		"./testing",
	]);
	expect(manifest.dependencies ?? {}).toEqual({});
	expect(manifest.peerDependencies?.react).toBeDefined();
	expect(manifest.peerDependenciesMeta?.react?.optional).toBe(true);
});

test("only ./react imports React, and only ./testing is a harness", () => {
	expect(importsOf("react.ts")).toContain("react");
	expect(importsOf("react.ts")).not.toContain("./testing");
	expect(importsOf("testing.ts")).not.toContain("react");
	for (const file of ["react.ts", "testing.ts"]) {
		const text = readFileSync(join(SRC, file), "utf8");
		expect(text, file).not.toMatch(BROWSER_GLOBALS);
	}
});
