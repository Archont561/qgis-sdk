/**
 * The shared Bunup preset must empty the output directory *before* Bun
 * writes into it, not concurrently.
 *
 * bunup 0.16.32 (`build()` in `src/build.ts`) calls `cleanOutDir()` without
 * awaiting it when `clean: true`, so the recursive `fs.rm` of a populated
 * `dist/` races the bundle that follows and can unlink files Bun has just
 * written. The autorelease gate hit exactly that on 2026-10-27 (run
 * 40547205008): `pixi run -e bun typecheck` left the bridge's `dist/` full,
 * turbo rebuilt it for `bun run test`, and bunup died with
 * `ENOENT: no such file or directory, open '.../dist/index.js'`.
 *
 * The preset therefore turns bunup's own `clean` off and empties the
 * directory from an awaited `onBuildStart` hook instead.
 */

import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import {
	mkdir,
	mkdtemp,
	readdir,
	realpath,
	rm,
	writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { bunupPreset, cleanOutDirBeforeBuild } from "../bunup.config.ts";

/** A throwaway package root; the hook resolves `outDir` against the cwd. */
let root = "";
const previousCwd = process.cwd();

beforeEach(async () => {
	root = await realpath(await mkdtemp(join(tmpdir(), "qgis-sdk-bunup-")));
	process.chdir(root);
});

afterEach(async () => {
	process.chdir(previousCwd);
	await rm(root, { recursive: true, force: true });
});

const start = (outDir: string) =>
	cleanOutDirBeforeBuild.hooks.onBuildStart?.({ options: { outDir } });

describe("bunupPreset", () => {
	test("does not let bunup clean the output directory itself", () => {
		expect(bunupPreset.clean).toBe(false);
	});

	test("cleans through an awaited build-start hook instead", () => {
		expect(bunupPreset.plugins).toContain(cleanOutDirBeforeBuild);
		expect(typeof cleanOutDirBeforeBuild.hooks.onBuildStart).toBe("function");
	});
});

describe("cleanOutDirBeforeBuild", () => {
	test("empties a populated output directory before resolving", async () => {
		const dist = join(root, "dist");
		await mkdir(join(dist, "shared"), { recursive: true });
		await writeFile(join(dist, "index.js"), "stale");
		await writeFile(join(dist, "shared", "chunk.js"), "stale");

		await start(dist);

		expect(existsSync(dist)).toBe(true);
		expect(await readdir(dist)).toEqual([]);
	});

	test("creates a missing output directory", async () => {
		await start(join(root, "dist"));

		expect(await readdir(join(root, "dist"))).toEqual([]);
	});

	test("resolves a relative output directory against the working directory", async () => {
		await writeFile(join(root, "keep.txt"), "keep");
		await mkdir(join(root, "out"));
		await writeFile(join(root, "out", "stale.js"), "stale");

		await start("out");

		expect(await readdir(join(root, "out"))).toEqual([]);
		expect(existsSync(join(root, "keep.txt"))).toBe(true);
	});

	test("refuses an output directory that is not below the working directory", async () => {
		await writeFile(join(root, "keep.txt"), "keep");

		await expect(start(".")).rejects.toThrow(/output directory/);
		await expect(start("..")).rejects.toThrow(/output directory/);
		await expect(start(join(root, "..", "elsewhere"))).rejects.toThrow(
			/output directory/,
		);

		expect(existsSync(join(root, "keep.txt"))).toBe(true);
	});
});
