/**
 * Report the prose words of guide-derived pages, one line each.
 *
 *     bun run scripts/measure-prose.ts content/docs/python/scoped-jobs.mdx …
 *     bun run scripts/measure-prose.ts --json        # every page under content/docs
 *
 * The definition of prose lives in `lib/prose.ts`, with the tests that pin it;
 * this file only walks the corpus and prints.
 */
import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { headingCount, proseWords } from "./lib/prose";

const DOCS = fileURLToPath(new URL("..", import.meta.url));
const CONTENT = join(DOCS, "content/docs");

/**
 * The generated trees whose words are not prose.
 *
 * `reference/python` holds the API reference fumero writes from signatures and
 * docstrings (decision-86): a parameter name and a type on their own line count
 * as words here, and there are a few thousand of them. Leaving it in would make
 * the corpus this metric reports a measure of the public surface rather than of
 * the pages someone wrote.
 */
const NOT_PROSE = new Set(["reference/python"]);

/** Every page under `content/docs`, as absolute paths. */
async function pages(directory = CONTENT): Promise<readonly string[]> {
	const entries = await readdir(directory, { withFileTypes: true });
	const out: string[] = [];
	for (const entry of entries) {
		const path = join(directory, entry.name);
		if (entry.isDirectory()) {
			if (NOT_PROSE.has(relative(CONTENT, path))) continue;
			out.push(...(await pages(path)));
			continue;
		}
		if (/\.mdx?$/.test(entry.name)) out.push(path);
	}
	return out.sort();
}

const args = process.argv.slice(2);
const json = args.includes("--json");
const targets = args.filter((arg) => arg.startsWith("-") === false);
const files = targets.length > 0 ? targets : await pages();
let total = 0;
const rows: Record<string, { words: number; headings: number }> = {};
for (const file of files) {
	const markdown = await readFile(file, "utf8");
	const words = proseWords(markdown);
	const headings = headingCount(markdown);
	total += words;
	rows[relative(CONTENT, file)] = { words, headings };
	if (json === false) {
		console.log(
			`${String(words).padStart(6)} ${String(headings).padStart(3)}  ${file}`,
		);
	}
}
if (json) {
	console.log(JSON.stringify(rows, null, "\t"));
} else {
	console.log(`${String(total).padStart(6)}       ${files.length} pages`);
}
