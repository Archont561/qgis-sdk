/**
 * The prose ratchet as a command (decision-86 item 2).
 *
 *     bun run scripts/ratchet.ts              # check the corpus against the budget
 *     bun run scripts/ratchet.ts --rebaseline # rewrite the budget from live prose
 *
 * The check is what `postbuild` runs: it fails when a page disagrees with its
 * allowance in either direction. Rebaselining rewrites `prose-budget.json`
 * from the live counts, keeping every recorded reason and adding an allowance
 * for a new page; it is a commit, not a flag in CI, so a widened allowance is
 * visible in review as a number going up. The allowance may only fall.
 */
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
	type Budget,
	loadBudget,
	ratchetProblems,
	readPages,
} from "./lib/ratchet";

const DOCS = fileURLToPath(new URL("..", import.meta.url));
const CONTENT = join(DOCS, "content/docs");
const BUDGET = join(DOCS, "prose-budget.json");

/** Rewrite the budget from the live counts, keeping the reasons. */
async function rebaseline(): Promise<void> {
	const [pages, budget] = await Promise.all([
		readPages(CONTENT),
		loadBudget(BUDGET).catch((): Budget => ({ version: 1, pages: {} })),
	]);
	const next: Record<string, { words: number; reason?: string }> = {};
	for (const page of pages) {
		const prior = budget.pages[page.source];
		next[page.source] =
			prior?.reason === undefined
				? { words: page.words }
				: { words: page.words, reason: prior.reason };
	}
	const widened = Object.entries(next).filter(
		([path, entry]) => (budget.pages[path]?.words ?? 0) < entry.words,
	);
	const text = `${JSON.stringify({ version: 1, pages: next }, null, "\t")}\n`;
	await writeFile(BUDGET, text, "utf8");
	console.log(
		`ratchet: rebaselined ${Object.keys(next).length} pages` +
			(widened.length > 0
				? `; ${widened.length} allowances widened: ${widened
						.map(([path]) => path)
						.join(", ")}`
				: ""),
	);
}

if (process.argv.includes("--rebaseline")) {
	await rebaseline();
} else {
	const problems = await ratchetProblems(CONTENT, BUDGET);
	for (const problem of problems) {
		console.error(`ratchet: ${problem.where}: ${problem.message}`);
	}
	console.log(`ratchet: ${problems.length} problems`);
	if (problems.length > 0) {
		process.exit(1);
	}
}
