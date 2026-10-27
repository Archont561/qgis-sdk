/**
 * What `npm pack` ships (task-70 AC #3, #5): `dist`, `README.md` and
 * `LICENSE` only - no sources, stories, Storybook config or tests - every
 * `exports` target inside it, and `lit` the one runtime dependency.
 *
 * `bun pm pack --dry-run` honours the same `files` whitelist npm does and
 * needs no registry; the package is built first when `dist/` is absent.
 */

import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import { join } from "node:path";

const PACKAGE = join(import.meta.dir, "..");

function run(args: readonly string[]): string {
	const result = Bun.spawnSync(["bun", ...args], {
		cwd: PACKAGE,
		stdout: "pipe",
		stderr: "pipe",
	});
	if (result.exitCode !== 0) {
		throw new Error(
			`bun ${args.join(" ")} failed: ${result.stderr.toString()}`,
		);
	}
	return result.stdout.toString();
}

if (!existsSync(join(PACKAGE, "dist", "index.js"))) {
	run(["run", "build"]);
}

const manifest = (await import("../package.json")) as {
	readonly files: readonly string[];
	readonly exports: Readonly<Record<string, unknown>>;
	readonly dependencies: Readonly<Record<string, string>>;
	readonly peerDependencies: Readonly<Record<string, string>>;
};

/** The paths `pack` would put in the tarball. */
function packedPaths(): readonly string[] {
	const output = run(["pm", "pack", "--dry-run"]);
	return output
		.split("\n")
		.filter((line) => line.startsWith("packed "))
		.map((line) => line.replace(/^packed \S+ /, "").trim());
}

/** Every file an `exports` entry points at, relative to the package. */
function exportTargets(value: unknown, out: string[] = []): string[] {
	if (typeof value === "string") {
		out.push(value.replace(/^\.\//, ""));
	} else if (value !== null && typeof value === "object") {
		for (const inner of Object.values(value)) {
			exportTargets(inner, out);
		}
	}
	return out;
}

describe("npm pack", () => {
	const paths = packedPaths();

	test("ships dist, README and LICENSE and nothing else", () => {
		expect(manifest.files).toEqual(["dist", "README.md", "LICENSE"]);
		expect(paths).toContain("package.json");
		expect(paths).toContain("README.md");
		expect(paths).toContain("LICENSE");
		const outside = paths.filter(
			(path) =>
				!path.startsWith("dist/") &&
				!["package.json", "README.md", "LICENSE"].includes(path),
		);
		expect(outside).toEqual([]);
		for (const forbidden of [
			"src/",
			"stories/",
			".storybook/",
			"tests/",
			"scripts/",
		]) {
			expect(paths.some((path) => path.startsWith(forbidden))).toBe(false);
		}
		expect(paths.some((path) => path.endsWith(".map"))).toBe(false);
	});

	test("every exports target and both stylesheets are in the tarball", () => {
		const targets = new Set(exportTargets(manifest.exports));
		expect(targets.size).toBeGreaterThan(0);
		for (const target of targets) {
			expect(paths).toContain(target);
		}
		expect(paths).toContain("dist/style.css");
		expect(paths).toContain("dist/tokens.css");
	});

	test("lit is the only dependency; the bridge and the frameworks are peers", () => {
		expect(Object.keys(manifest.dependencies)).toEqual(["lit"]);
		expect(Object.keys(manifest.peerDependencies).sort()).toEqual([
			"@archont561/qgis-sdk",
			"@lit/react",
			"react",
			"svelte",
			"vue",
		]);
	});
});
