/**
 * Compile `dist/style.css` and `dist/tokens.css` from the package's own
 * sources (task-70 AC #6).
 *
 * UnoCSS reads the `qs-` classes the elements' templates use - and nothing
 * else: no preflight, no safelist - and the preset's theme binds every colour
 * to a `--qgis-sdk-*` token. The tokens' defaults go first, so the stylesheet
 * stands alone outside QGIS. The size budget below is the documented one; a
 * build over it fails here, not in a consumer's bundle.
 */

import {
	mkdirSync,
	readdirSync,
	readFileSync,
	statSync,
	writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createGenerator } from "@unocss/core";
import { tokensStylesheet } from "../src/tokens";
import { presetQgisSdk } from "../src/uno";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/** The documented ceiling of `dist/style.css`, in bytes. */
export const STYLE_BUDGET_BYTES: number = 12 * 1024;

/** Every `.ts` under `src/`, the only sources the classes are read from. */
export function sourceFiles(root: string = ROOT): string[] {
	const files: string[] = [];
	const walk = (directory: string): void => {
		for (const entry of readdirSync(directory)) {
			const path = join(directory, entry);
			if (statSync(path).isDirectory()) {
				walk(path);
			} else if (entry.endsWith(".ts")) {
				files.push(path);
			}
		}
	};
	walk(join(root, "src"));
	return files.sort();
}

export interface BuiltStyle {
	/** `style.css`: the tokens' defaults, then the utilities the sources use. */
	readonly style: string;
	/** `tokens.css`: the defaults alone. */
	readonly tokens: string;
	/** The utilities that matched, for a test to look at. */
	readonly matched: readonly string[];
}

/** Compile the stylesheets from the sources without writing anything. */
export async function buildStyle(root: string = ROOT): Promise<BuiltStyle> {
	const generator = await createGenerator({ presets: [presetQgisSdk()] });
	const code = sourceFiles(root)
		.map((file) => readFileSync(file, "utf8"))
		.join("\n");
	const result = await generator.generate(code, {
		preflights: false,
		minify: false,
	});
	const tokens = tokensStylesheet();
	const header =
		"/* @archont561/qgis-sdk-ui - compiled by UnoCSS preset-mini from the package sources */\n";
	return {
		style: `${header}${tokens}\n${result.css}\n`,
		tokens: `${header}${tokens}`,
		matched: [...result.matched].sort(),
	};
}

/** Write both stylesheets under `dist/`, refusing a `style.css` over budget. */
export async function writeStyle(
	root: string = ROOT,
	budget: number = STYLE_BUDGET_BYTES,
): Promise<BuiltStyle> {
	const built = await buildStyle(root);
	const size = Buffer.byteLength(built.style, "utf8");
	if (size > budget) {
		throw new Error(
			`dist/style.css is ${size} bytes, over the ${budget}-byte budget`,
		);
	}
	const dist = join(root, "dist");
	mkdirSync(dist, { recursive: true });
	writeFileSync(join(dist, "style.css"), built.style);
	writeFileSync(join(dist, "tokens.css"), built.tokens);
	console.log(
		`style.css ${size} bytes (${built.matched.length} utilities), tokens.css ${Buffer.byteLength(built.tokens, "utf8")} bytes`,
	);
	return built;
}

if (import.meta.main) {
	await writeStyle();
}
