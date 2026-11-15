/**
 * The directive layer: plain text in, JSX out, with the error a wrong marker
 * deserves.
 *
 * The guide sources are read on GitHub, so a component cannot be written as
 * JSX there. These tests hold the three promises the layer makes: ordinary
 * markdown passes through untouched, each directive expands to the component it
 * names and records that name for the build gate, and a malformed marker is an
 * error with a line number rather than a `:::steps` left in the prose.
 */
import { describe, expect, test } from "bun:test";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import {
	DirectiveError,
	directiveText,
	expandDirectives,
} from "../scripts/lib/directives";
import { jsxInMarkdown } from "../scripts/lib/gate";

describe("expandDirectives", () => {
	test("leaves markdown without directives byte-identical", () => {
		const source = "# Title\n\nA paragraph with [a link](/python).\n";
		expect(expandDirectives(source)).toEqual({
			markdown: source,
			components: [],
		});
	});

	test("keeps the prose around a block and wraps the component", () => {
		const { markdown, components } = expandDirectives(
			'Before.\n\n:::callout type=warning title="Heads up"\nBody.\n:::\n\nAfter.\n',
		);
		expect(components).toEqual(["callout"]);
		expect(markdown).toContain("Before.\n");
		expect(markdown).toContain("After.\n");
		expect(markdown).toContain('<div data-qgis-sdk="callout">');
		expect(markdown).toContain('<Callout type="warning" title="Heads up">');
		expect(markdown).toContain("Body.");
	});

	test("defaults a callout to the info type", () => {
		const { markdown } = expandDirectives(":::callout\nBody.\n:::\n");
		expect(markdown).toContain('<Callout type="info">');
	});

	test("rejects a callout type the component does not take", () => {
		expect(() => expandDirectives(":::callout type=loud\nx\n:::\n")).toThrow(
			/unknown callout type loud/,
		);
	});

	test("turns an ordered list into steps, fence included", () => {
		const { markdown, components } = expandDirectives(
			":::steps\n1. Install:\n\n   ```bash\n   pip install qgis-sdk\n   ```\n\n2. Run it.\n:::\n",
		);
		expect(components).toEqual(["steps"]);
		expect(markdown).toContain('<div data-qgis-sdk="steps">');
		expect(markdown.match(/<Step>/g)).toHaveLength(2);
		expect(markdown).toContain("```bash");
		expect(markdown).toContain("pip install qgis-sdk");
		expect(markdown).toContain("2. Run it.".replace("2. ", ""));
	});

	test("rejects steps that are not a list", () => {
		expect(() => expandDirectives(":::steps\nJust prose.\n:::\n")).toThrow(
			/:::steps holds an ordered list/,
		);
	});

	test("turns tab blocks into one Tabs, labels and all", () => {
		const { markdown, components } = expandDirectives(
			":::tabs\n:::tab pip\nFrom PyPI.\n:::\n:::tab pixi\nFrom prefix.dev.\n:::\n:::\n",
		);
		expect(components).toEqual(["tabs", "tab"]);
		expect(markdown).toContain(
			'<Tabs items={["pip", "pixi"]} defaultValue="pip">',
		);
		expect(markdown).toContain('<Tab value="pip">');
		expect(markdown).toContain('<Tab value="pixi">');
	});

	test("rejects a tab outside tabs", () => {
		expect(() => expandDirectives(":::tab pip\nx\n:::\n")).toThrow(
			/:::tab belongs in :::tabs/,
		);
	});

	test("rejects text between tabs", () => {
		expect(() =>
			expandDirectives(":::tabs\nstray\n:::tab pip\nx\n:::\n:::\n"),
		).toThrow(/:::tabs holds only :::tab blocks/);
	});

	test("renders a file tree with folders and files", () => {
		const { markdown, components } = expandDirectives(
			":::files\n- my-plugin/\n  - plugin.py\n  - tests/\n    - test_plugin.py\n- README.md\n:::\n",
		);
		expect(components).toEqual(["files"]);
		expect(markdown).toContain('<Folder name="my-plugin" defaultOpen>');
		expect(markdown).toContain('<Folder name="tests" defaultOpen>');
		expect(markdown).toContain('<File name="plugin.py" />');
		expect(markdown).toContain('<File name="test_plugin.py" />');
		expect(markdown).toContain('<File name="README.md" />');
	});

	test("rejects a files block that is not a bullet tree", () => {
		expect(() => expandDirectives(":::files\nplugin.py\n:::\n")).toThrow(
			/:::files holds a bullet tree/,
		);
	});

	test("renders accordions with an anchor derived from the title", () => {
		const { markdown, components } = expandDirectives(
			':::accordions\n:::accordion title="Why a callback?"\nBecause.\n:::\n' +
				':::accordion title="Where does it run?" id="where"\nHere.\n:::\n:::\n',
		);
		expect(components).toEqual(["accordions", "accordion"]);
		expect(markdown).toContain(
			'<Accordion title="Why a callback?" id="why-a-callback">',
		);
		expect(markdown).toContain(
			'<Accordion title="Where does it run?" id="where">',
		);
	});

	test("rejects an accordion without a title", () => {
		expect(() =>
			expandDirectives(":::accordions\n:::accordion\nx\n:::\n:::\n"),
		).toThrow(/:::accordion needs a title/);
	});

	test("rejects an unknown directive by name", () => {
		expect(() => expandDirectives(":::gallery\nx\n:::\n")).toThrow(
			/unknown directive :::gallery/,
		);
	});

	test("rejects a block that is never closed", () => {
		expect(() => expandDirectives(":::callout\nx\n")).toThrow(
			/directive on line 1: :::callout is never closed/,
		);
	});

	test("rejects a closing marker with nothing open", () => {
		expect(() => expandDirectives("x\n:::\n")).toThrow(
			/directive on line 2: `:::` closes a block that was never opened/,
		);
	});

	test("treats a directive inside a fence as text", () => {
		const source = "```text\n:::steps\n1. x\n:::\n```\n";
		expect(expandDirectives(source)).toEqual({
			markdown: source,
			components: [],
		});
	});

	test("rejects an empty steps block", () => {
		expect(() => expandDirectives(":::steps\n\n:::\n")).toThrow(
			/:::steps has no steps/,
		);
	});

	test("rejects an empty files block", () => {
		expect(() => expandDirectives(":::files\n\n:::\n")).toThrow(
			/:::files is empty/,
		);
	});

	test("rejects a file tree that indents by something other than two", () => {
		expect(() => expandDirectives(":::files\n- a\n   - b\n:::\n")).toThrow(
			/:::files indents by two spaces/,
		);
	});

	test("rejects a file tree that skips a level", () => {
		expect(() => expandDirectives(":::files\n- a\n    - b\n:::\n")).toThrow(
			/:::files indents b too deep/,
		);
	});

	test("rejects a tab with no label", () => {
		expect(() => expandDirectives(":::tabs\n:::tab\nx\n:::\n:::\n")).toThrow(
			/:::tab needs a label/,
		);
	});

	test("rejects an empty tabs block", () => {
		expect(() => expandDirectives(":::tabs\n\n:::\n")).toThrow(
			/:::tabs has no :::tab blocks/,
		);
	});

	test("rejects an empty accordions block", () => {
		expect(() => expandDirectives(":::accordions\n\n:::\n")).toThrow(
			/:::accordions has no :::accordion blocks/,
		);
	});

	test("points at the line of a bad nested marker", () => {
		expect(() =>
			expandDirectives(":::callout\n:::steps\n1. x\n:::\n:::\n"),
		).toThrow(/directive on line 2: :::steps cannot sit inside :::callout/);
	});

	test("escapes a quote in a title instead of ending the attribute", () => {
		const { markdown } = expandDirectives(
			':::callout title="The \\"run\\" command"\nBody.\n:::\n',
		);
		expect(markdown).toContain(
			'<Callout type="info" title="The \\"run\\" command">',
		);
	});
});

describe("directiveText", () => {
	test("drops the markers and keeps the body", () => {
		expect(directiveText("Intro.\n\n:::callout\nThe body.\n:::\n")).toBe(
			"Intro.\n\nThe body.\n",
		);
	});

	test("leaves a page with no directives alone", () => {
		expect(directiveText("Plain **markdown**.\n")).toBe(
			"Plain **markdown**.\n",
		);
	});
});

describe("DirectiveError", () => {
	test("carries the line and a readable message", () => {
		const error = new DirectiveError(7, "something is wrong");
		expect(error.message).toBe("directive on line 7: something is wrong");
		expect(error.name).toBe("DirectiveError");
	});
});

describe("the guide sources", () => {
	const GUIDES = join(import.meta.dir, "../../..", "apps/docs/guides");

	async function guides(): Promise<readonly string[]> {
		const names = (await readdir(GUIDES)).filter((name) =>
			name.endsWith(".md"),
		);
		return Promise.all(
			names.map((name) => readFile(join(GUIDES, name), "utf8")),
		);
	}

	test("carry no JSX, so GitHub shows prose and not tags", async () => {
		// The sources are read on GitHub as the canonical explanation
		// (decision-29); a component there is a wall of tags in the file, and the
		// same block in a `.md` page is dropped without an error. The check is the
		// gate's own, so a code span like `BridgeSchema<O, S>` is not mistaken
		// for a component.
		const names = (await readdir(GUIDES)).filter((name) =>
			name.endsWith(".md"),
		);
		const pages = await Promise.all(
			names.map(async (name) => ({
				source: name,
				body: await readFile(join(GUIDES, name), "utf8"),
			})),
		);
		expect(jsxInMarkdown(pages)).toEqual([]);
	});

	test("expand cleanly, so no directive is left unparsed", async () => {
		for (const markdown of await guides()) {
			// A guide with no directives returns its own text; one with them comes
			// back as JSX. Either way the parse is the check: a stray marker, an
			// unknown name or an unclosed block throws here rather than shipping.
			const expanded = expandDirectives(markdown);
			expect(expanded.components).toBeInstanceOf(Array);
		}
	});
});
