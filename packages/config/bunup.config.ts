import { mkdir, rm } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";

/** The slice of bunup's plugin contract the preset needs; no import, so the
 * preset stays a plain module every package can load without bunup's types. */
type BuildStartContext = { options: { outDir?: string } };
type BunupPlugin = {
	name: string;
	hooks: { onBuildStart?: (ctx: BuildStartContext) => Promise<void> };
};

/**
 * Empty the output directory and *wait* for it before Bun writes a file.
 *
 * bunup's own `clean: true` (0.16.32, `build()` in `src/build.ts`) calls
 * `cleanOutDir()` without awaiting it, so the recursive `rm` of a populated
 * `dist/` runs alongside the bundle and can unlink what Bun has just written:
 * `ENOENT: no such file or directory, open 'dist/index.js'`. It bit the
 * autorelease gate on 2026-10-27 (run 40547205008), where `typecheck` had
 * filled the bridge's `dist/` and turbo rebuilt it for `bun run test`.
 * Plugin `onBuildStart` hooks are awaited, so the clean lands here instead.
 *
 * `outDir` is resolved against the working directory bunup runs in (the
 * package root) and must stay strictly below it.
 */
export const cleanOutDirBeforeBuild: BunupPlugin = {
	name: "qgis-sdk:clean-out-dir",
	hooks: {
		async onBuildStart({ options }) {
			const root = process.cwd();
			const outDir = resolve(root, options.outDir ?? "dist");
			const below = relative(root, outDir);
			if (!below || below.startsWith("..") || isAbsolute(below)) {
				throw new Error(
					`refusing to clean output directory ${outDir}: it is not below ${root}`,
				);
			}
			await rm(outDir, { recursive: true, force: true });
			await mkdir(outDir, { recursive: true });
		},
	},
};

export const bunupPreset = {
	format: ["esm"] as const,
	target: "node" as const,
	dts: true,
	// Off on purpose: see `cleanOutDirBeforeBuild`.
	clean: false,
	sourcemap: true,
	plugins: [cleanOutDirBeforeBuild],
};

export default bunupPreset;
