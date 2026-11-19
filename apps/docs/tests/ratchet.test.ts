/**
 * The prose ratchet, on the cases that decide whether it bites.
 *
 * Decision-86 item 2 enforces the per-kind prose budgets as a ratchet, not an
 * aspiration: a page that grows past its allowance fails, and a page that
 * falls under its allowance fails until the allowance is lowered in the same
 * change. The allowance may only fall. A page over its kind's budget is
 * allowed only with a recorded reason. These tests pin each arm.
 */
import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
	type Budget,
	checkRatchet,
	loadBudget,
	parseBudget,
	type RatchetPage,
	ratchetProblems,
	readPages,
} from "../scripts/lib/ratchet";

function page(
	source: string,
	kind: RatchetPage["kind"],
	words: number,
): RatchetPage {
	return { source, kind, words };
}

function budget(
	pages: Record<string, { words: number; reason?: string }>,
): Budget {
	return { version: 1, pages };
}

describe("checkRatchet", () => {
	test("a page holding its allowance exactly passes", () => {
		const problems = checkRatchet(
			[page("python/installation.mdx", "tutorial", 346)],
			budget({ "python/installation.mdx": { words: 346 } }),
		);
		expect(problems).toEqual([]);
	});

	test("a page that grew past its allowance fails", () => {
		const problems = checkRatchet(
			[page("python/installation.mdx", "tutorial", 400)],
			budget({ "python/installation.mdx": { words: 346 } }),
		);
		expect(problems).toHaveLength(1);
		expect(problems[0]?.message).toContain("grew to 400");
		expect(problems[0]?.message).toContain("allowance of 346");
	});

	test("a page that fell under its allowance fails until it is lowered", () => {
		const problems = checkRatchet(
			[page("python/installation.mdx", "tutorial", 300)],
			budget({ "python/installation.mdx": { words: 346 } }),
		);
		expect(problems).toHaveLength(1);
		expect(problems[0]?.message).toContain("fell to 300");
		expect(problems[0]?.message).toContain("lower the allowance");
	});

	test("a page with no kind fails", () => {
		const problems = checkRatchet(
			[page("python/installation.mdx", null, 10)],
			budget({ "python/installation.mdx": { words: 10 } }),
		);
		expect(problems).toHaveLength(1);
		expect(problems[0]?.message).toContain("declares no kind");
	});

	test("a page with no allowance fails", () => {
		const problems = checkRatchet(
			[page("python/installation.mdx", "tutorial", 10)],
			budget({}),
		);
		expect(problems).toHaveLength(1);
		expect(problems[0]?.message).toContain("has no allowance");
	});

	test("a page over its kind budget with no reason fails", () => {
		const problems = checkRatchet(
			[page("python/scoped-jobs.mdx", "how-to", 2128)],
			budget({ "python/scoped-jobs.mdx": { words: 2128 } }),
		);
		expect(problems).toHaveLength(1);
		expect(problems[0]?.message).toContain("over the how-to budget of 700");
		expect(problems[0]?.message).toContain("record a reason");
	});

	test("a page over its kind budget with a reason passes", () => {
		const problems = checkRatchet(
			[page("python/scoped-jobs.mdx", "how-to", 2128)],
			budget({
				"python/scoped-jobs.mdx": {
					words: 2128,
					reason: "Conversion scheduled; the allowance may only fall.",
				},
			}),
		);
		expect(problems).toEqual([]);
	});

	test("a page within its kind budget needs no reason", () => {
		const problems = checkRatchet(
			[page("python/installation.mdx", "tutorial", 346)],
			budget({ "python/installation.mdx": { words: 346 } }),
		);
		expect(problems).toEqual([]);
	});

	test("a budget entry for a page that no longer exists fails", () => {
		const problems = checkRatchet(
			[],
			budget({ "python/gone.mdx": { words: 10 } }),
		);
		expect(problems).toHaveLength(1);
		expect(problems[0]?.message).toContain("no page");
	});

	test("each kind carries its own ceiling", () => {
		// 500 words is within a tutorial (1,200) and an explanation (1,500) but
		// over a reference (400) and a how-to (700 is not over; 800 is).
		const within = checkRatchet(
			[page("a.mdx", "tutorial", 500), page("b.mdx", "explanation", 500)],
			budget({ "a.mdx": { words: 500 }, "b.mdx": { words: 500 } }),
		);
		expect(within).toEqual([]);
		const over = checkRatchet(
			[page("c.mdx", "reference", 500), page("d.mdx", "how-to", 800)],
			budget({ "c.mdx": { words: 500 }, "d.mdx": { words: 800 } }),
		);
		expect(over).toHaveLength(2);
	});
});

describe("parseBudget", () => {
	test("reads a budget with and without reasons", () => {
		const parsed = parseBudget(
			JSON.stringify({
				version: 1,
				pages: {
					"a.mdx": { words: 10 },
					"b.mdx": { words: 20, reason: "Why." },
				},
			}),
		);
		expect(parsed.pages["a.mdx"]).toEqual({ words: 10 });
		expect(parsed.pages["b.mdx"]).toEqual({ words: 20, reason: "Why." });
	});

	test("rejects a document that is not JSON", () => {
		expect(() => parseBudget("not json")).toThrow("not valid JSON");
	});

	test("rejects an entry with no word count", () => {
		expect(() =>
			parseBudget(JSON.stringify({ pages: { "a.mdx": { reason: "Why." } } })),
		).toThrow("no word count");
	});

	test("rejects a negative word count", () => {
		expect(() =>
			parseBudget(JSON.stringify({ pages: { "a.mdx": { words: -1 } } })),
		).toThrow("no word count");
	});
});

describe("the corpus readers", () => {
	async function corpus(files: Record<string, string>): Promise<string> {
		const dir = await mkdtemp(join(tmpdir(), "ratchet-"));
		for (const [name, content] of Object.entries(files)) {
			const path = join(dir, name);
			await mkdir(join(path, ".."), { recursive: true });
			await writeFile(path, content, "utf8");
		}
		return dir;
	}

	test("readPages reads the kind and the prose count, skipping the reference", async () => {
		const dir = await corpus({
			"python/a.mdx": '---\ntitle: "A"\nkind: how-to\n---\nTwo words here.\n',
			"b.md": "---\ntitle: B\n---\nNo kind declared.\n",
			"reference/python/c.mdx":
				"---\ntitle: C\nkind: reference\n---\nIgnored.\n",
		});
		const pages = await readPages(dir);
		expect(pages).toHaveLength(2);
		const a = pages.find((p) => p.source === "python/a.mdx");
		expect(a?.kind).toBe("how-to");
		expect(a?.words).toBe(3);
		const b = pages.find((p) => p.source === "b.md");
		expect(b?.kind).toBeNull();
	});

	test("readPages reads a quoted kind", async () => {
		const dir = await corpus({
			"a.mdx": '---\ntitle: "A"\nkind: "tutorial"\n---\nOne.\n',
		});
		const pages = await readPages(dir);
		expect(pages[0]?.kind).toBe("tutorial");
	});

	test("loadBudget reads the committed budget", async () => {
		const dir = await corpus({
			"prose-budget.json": JSON.stringify({
				version: 1,
				pages: { "a.mdx": { words: 3 } },
			}),
		});
		const budget = await loadBudget(join(dir, "prose-budget.json"));
		expect(budget.pages["a.mdx"]).toEqual({ words: 3 });
	});

	test("ratchetProblems is clean when the corpus holds its budget", async () => {
		const dir = await corpus({
			"a.mdx": '---\ntitle: "A"\nkind: tutorial\n---\nOne two three.\n',
			"prose-budget.json": JSON.stringify({
				version: 1,
				pages: { "a.mdx": { words: 3 } },
			}),
		});
		expect(await ratchetProblems(dir, join(dir, "prose-budget.json"))).toEqual(
			[],
		);
	});

	test("ratchetProblems reports a page that grew", async () => {
		const dir = await corpus({
			"a.mdx": '---\ntitle: "A"\nkind: tutorial\n---\nOne two three four.\n',
			"prose-budget.json": JSON.stringify({
				version: 1,
				pages: { "a.mdx": { words: 3 } },
			}),
		});
		const problems = await ratchetProblems(dir, join(dir, "prose-budget.json"));
		expect(problems).toHaveLength(1);
		expect(problems[0]?.message).toContain("grew to 4");
	});
});
