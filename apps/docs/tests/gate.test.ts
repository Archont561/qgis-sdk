/**
 * The component gate: the two silent failures a green build cannot see.
 *
 * Probe A put `<Steps>` in a `.mdx` page without registering it and got
 * `Expected component Steps to be defined` - loud, and fine. Probe B put the
 * same component in a `.md` page: the build passed, the page shipped, and the
 * wrappers were gone. Nothing in the HTML said so. These tests hold the gate
 * that catches the second case, and the marker check that catches any page
 * whose directive did not become markup.
 */
import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { mdxComponents } from "../lib/mdx";
import {
	jsxInMarkdown,
	markerOf,
	missingComponentMarkup,
} from "../scripts/lib/gate";

const ROOT = join(import.meta.dir, "../../..");

describe("jsxInMarkdown", () => {
	test("reports a component in a .md page, with its line", () => {
		const problems = jsxInMarkdown([
			{
				source: "start/installation.md",
				body: "Intro.\n\n<Steps>\n<Step>Install.</Step>\n</Steps>\n",
			},
		]);
		expect(problems).toEqual([
			{
				where: "start/installation.md:3",
				message:
					"<Steps> is JSX in a .md page, which markdown drops; rename the page to .mdx or write a directive",
			},
		]);
	});

	test("says nothing about the same tag in an .mdx page", () => {
		expect(
			jsxInMarkdown([{ source: "start/installation.mdx", body: "<Steps />" }]),
		).toEqual([]);
	});

	test("passes a .md page whose only angle brackets are prose", () => {
		const problems = jsxInMarkdown([
			{
				source: "reference/faq.md",
				body: "Use `<br>` for a break, and see <https://example.com>.\n",
			},
		]);
		expect(problems).toEqual([]);
	});

	test("names only the first offending line of a page", () => {
		const problems = jsxInMarkdown([
			{ source: "a.md", body: "<Callout>\nx\n</Callout>\n" },
		]);
		expect(problems).toHaveLength(1);
		expect(problems[0]?.where).toBe("a.md:1");
	});

	test("reports every page that has one", () => {
		const problems = jsxInMarkdown([
			{ source: "a.md", body: "<Tabs />" },
			{ source: "b.md", body: "clean\n" },
			{ source: "c.md", body: "<Files />" },
		]);
		expect(problems.map((problem) => problem.where)).toEqual([
			"a.md:1",
			"c.md:1",
		]);
	});
});

describe("markerOf", () => {
	test("is the attribute the expansion writes", () => {
		expect(markerOf("steps")).toBe('data-qgis-sdk="steps"');
	});
});

describe("missingComponentMarkup", () => {
	const read =
		(pages: Readonly<Record<string, string>>) =>
		async (route: string): Promise<string | null> =>
			pages[route] ?? null;

	test("passes when every recorded component is in the HTML", async () => {
		const problems = await missingComponentMarkup(
			{ "/python/scoped-jobs": ["accordions", "accordion"] },
			read({
				"/python/scoped-jobs":
					'<div data-qgis-sdk="accordions"><div data-qgis-sdk="accordion">',
			}),
		);
		expect(problems).toEqual([]);
	});

	test("reports a component whose marker is absent", async () => {
		const problems = await missingComponentMarkup(
			{ "/python/scoped-jobs": ["accordions", "callout"] },
			read({ "/python/scoped-jobs": '<div data-qgis-sdk="accordions">' }),
		);
		expect(problems).toEqual([
			{
				where: "/python/scoped-jobs",
				message:
					':::callout produced no data-qgis-sdk="callout" in the page; the component was dropped instead of rendered',
			},
		]);
	});

	test("reports a route that was never exported", async () => {
		const problems = await missingComponentMarkup(
			{ "/python/gone": ["steps"] },
			read({}),
		);
		expect(problems).toEqual([
			{
				where: "/python/gone",
				message: "carries components but was not exported; check the route",
			},
		]);
	});

	test("passes when no page records a component", async () => {
		expect(await missingComponentMarkup({}, read({}))).toEqual([]);
	});
});

describe("the site as generated", () => {
	test("every component the generator records is in the registry", async () => {
		// The record is written by `bun run generate`; a checkout that has not
		// run it yet has no file, and this test then asserts nothing it cannot
		// know rather than failing on a missing artefact.
		const file = Bun.file(
			join(ROOT, "apps/docs/lib/generated/components.json"),
		);
		if ((await file.exists()) === false) return;
		const use = (await file.json()) as Record<string, readonly string[]>;
		for (const names of Object.values(use)) {
			for (const name of names) {
				// `callout` -> `Callout`: the expander names the block, the
				// registry names the component.
				expect(mdxComponents).toHaveProperty(capitalise(name));
			}
		}
	});
});

/** `callout` -> `Callout`: a directive name to the component it renders. */
function capitalise(name: string): string {
	return `${name.charAt(0).toUpperCase()}${name.slice(1)}`;
}
