/**
 * The prose ratchet: a committed budget of exact word counts, enforced in
 * either direction (decision-86 item 2, decision-80's shape).
 *
 * Every page declares a `kind` in its frontmatter and carries a prose budget
 * from that kind (tutorial 1,200, how-to 700, reference 400 outside tables,
 * explanation 1,500). `prose-budget.json` records the exact allowance for each
 * page. The gate fails when a page disagrees with its allowance in either
 * direction:
 *
 * - a page that grows past its allowance fails: new prose is a regression;
 * - a page that falls under its allowance fails until the allowance is lowered
 *   in the same change, so headroom cannot hide where the next regression
 *   lives. The allowance may only fall.
 *
 * A page over its kind's budget is allowed to exist, but only with a recorded
 * reason: the ratchet starts from the corpus as it is, and each later
 * conversion lowers one line. No page is exempt.
 *
 * The measurement is `proseWords` (`lib/prose.ts`), the same function
 * `measure-prose` reports, so the budget and the gate cannot disagree about
 * what a word is. The fumero reference (`reference/python/`) is excluded: it
 * is generated from docstrings, which carry their own budget (CC101).
 *
 * The check is pure - the caller hands in the pages and the budget - so the
 * tests run it on fixtures. The IO (walking the corpus, loading the budget)
 * lives here too, so `postbuild` and the CLI share one implementation.
 */
import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";
import type { GateProblem } from "./gate";
import { isKind, KIND_BUDGETS, type Kind } from "./kinds";
import { proseWords } from "./prose";

/** One page as the ratchet reads it. */
export interface RatchetPage {
	/** Path under `content/docs`, e.g. `python/scoped-jobs.mdx`. */
	readonly source: string;
	/** The declared kind, or `null` when the frontmatter has none. */
	readonly kind: Kind | null;
	/** Prose words outside tables and code. */
	readonly words: number;
}

/** One page's allowance in the budget. */
export interface BudgetEntry {
	/** The exact prose count the page must hold. */
	readonly words: number;
	/** Why the page is over its kind's budget, when it is. */
	readonly reason?: string;
}

/** The committed budget: an exact allowance per page. */
export interface Budget {
	readonly version: number;
	readonly pages: Readonly<Record<string, BudgetEntry>>;
}

/** The generated tree whose words are not prose (see `measure-prose`). */
const NOT_PROSE = new Set(["reference/python"]);

/** The `kind:` line of a page's frontmatter, or `null`. */
function declaredKind(markdown: string): Kind | null {
	const match = /^---\n[\s\S]*?\n---\n/.exec(markdown);
	if (match === null) {
		return null;
	}
	const line = /^kind:\s*(.+)$/m.exec(match[0]);
	if (line === null) {
		return null;
	}
	const value = (line[1] ?? "").trim().replace(/^(['"])([\s\S]*)\1$/, "$2");
	return isKind(value) ? value : null;
}

/** Every page under a content directory, as absolute paths. */
async function pageFiles(
	contentDir: string,
	directory: string,
): Promise<readonly string[]> {
	const entries = await readdir(directory, { withFileTypes: true });
	const out: string[] = [];
	for (const entry of entries) {
		const path = join(directory, entry.name);
		if (entry.isDirectory()) {
			if (NOT_PROSE.has(relative(contentDir, path))) {
				continue;
			}
			out.push(...(await pageFiles(contentDir, path)));
			continue;
		}
		if (/\.mdx?$/.test(entry.name)) {
			out.push(path);
		}
	}
	return out.sort();
}

/** Read every page of the corpus: its kind and its prose count. */
export async function readPages(
	contentDir: string,
): Promise<readonly RatchetPage[]> {
	const pages: RatchetPage[] = [];
	for (const file of await pageFiles(contentDir, contentDir)) {
		const markdown = await readFile(file, "utf8");
		pages.push({
			source: relative(contentDir, file).split("\\").join("/"),
			kind: declaredKind(markdown),
			words: proseWords(markdown),
		});
	}
	return pages;
}

/** Parse and validate the committed budget. */
export function parseBudget(text: string): Budget {
	let parsed: unknown;
	try {
		parsed = JSON.parse(text);
	} catch {
		throw new Error("prose-budget.json is not valid JSON");
	}
	if (typeof parsed !== "object" || parsed === null) {
		throw new Error("prose-budget.json must be an object");
	}
	const record = parsed as Record<string, unknown>;
	const pages = record.pages;
	if (typeof pages !== "object" || pages === null) {
		throw new Error("prose-budget.json has no pages object");
	}
	const entries: Record<string, BudgetEntry> = {};
	for (const [path, value] of Object.entries(pages)) {
		if (typeof value !== "object" || value === null) {
			throw new Error(`prose-budget.json: ${path} is not an entry`);
		}
		const entry = value as Record<string, unknown>;
		const words = entry.words;
		if (typeof words !== "number" || !Number.isInteger(words) || words < 0) {
			throw new Error(`prose-budget.json: ${path} has no word count`);
		}
		const reason = entry.reason;
		if (reason !== undefined && typeof reason !== "string") {
			throw new Error(`prose-budget.json: ${path} has a non-text reason`);
		}
		entries[path] = reason === undefined ? { words } : { words, reason };
	}
	return {
		version: typeof record.version === "number" ? record.version : 1,
		pages: entries,
	};
}

/** Load the committed budget from disk. */
export async function loadBudget(path: string): Promise<Budget> {
	return parseBudget(await readFile(path, "utf8"));
}

/**
 * Every way the corpus disagrees with the budget, in either direction.
 *
 * A page that grew past its allowance, a page that fell under it without the
 * allowance being lowered, a page with no kind or no allowance, a page over
 * its kind's budget with no reason, and a budget entry for a page that no
 * longer exists are all problems. The fix is always in the same diff: trim
 * the prose, or lower the allowance to match it.
 */
export function checkRatchet(
	pages: readonly RatchetPage[],
	budget: Budget,
): readonly GateProblem[] {
	const problems: GateProblem[] = [];
	const seen = new Set<string>();
	for (const page of pages) {
		seen.add(page.source);
		if (page.kind === null) {
			problems.push({
				where: page.source,
				message:
					"declares no kind; every page names the need it serves " +
					"(tutorial, how-to, reference or explanation)",
			});
			continue;
		}
		const entry = budget.pages[page.source];
		if (entry === undefined) {
			problems.push({
				where: page.source,
				message: `has no allowance in prose-budget.json; add one for ${page.words} words`,
			});
			continue;
		}
		if (page.words > entry.words) {
			problems.push({
				where: page.source,
				message:
					`grew to ${page.words} words, over its allowance of ` +
					`${entry.words}; trim the prose - the allowance may only fall`,
			});
		} else if (page.words < entry.words) {
			problems.push({
				where: page.source,
				message:
					`fell to ${page.words} words, under its allowance of ` +
					`${entry.words}; lower the allowance in prose-budget.json to match`,
			});
		}
		const ceiling = KIND_BUDGETS[page.kind];
		if (page.words > ceiling && entry.reason === undefined) {
			problems.push({
				where: page.source,
				message:
					`is ${page.words} words, over the ${page.kind} budget of ` +
					`${ceiling}; record a reason in prose-budget.json or trim it`,
			});
		}
	}
	for (const path of Object.keys(budget.pages)) {
		if (seen.has(path)) {
			continue;
		}
		problems.push({
			where: path,
			message:
				"has an allowance but no page; remove the entry or restore the page",
		});
	}
	return problems;
}

/** The ratchet over a content directory and a budget file on disk. */
export async function ratchetProblems(
	contentDir: string,
	budgetPath: string,
): Promise<readonly GateProblem[]> {
	const [pages, budget] = await Promise.all([
		readPages(contentDir),
		loadBudget(budgetPath),
	]);
	return checkRatchet(pages, budget);
}
