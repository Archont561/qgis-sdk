/**
 * The prose measurement, on the cases that decide whether a number moves.
 *
 * "25 percent less text" is the acceptance criterion of the phase this script
 * serves, so the definition of "text" is the thing under test: code is not
 * prose, a table row is not prose, and a directive marker is not prose. A
 * measurement that counted any of them would report a conversion as a reduction
 * when all it did was move a catalogue into a table.
 */
import { describe, expect, test } from "bun:test";
import { headingCount, proseOf, proseWords } from "../scripts/lib/prose";

describe("proseWords", () => {
	test("counts the body and not the frontmatter", () => {
		expect(proseWords('---\ntitle: "A"\n---\nTwo words.\n')).toBe(2);
	});

	test("drops a fenced block, which is code rather than prose", () => {
		expect(
			proseWords("One two.\n\n```python\nimport os\n```\n\nThree.\n"),
		).toBe(3);
	});

	test("drops table rows, which are a lookup", () => {
		expect(
			proseWords(
				"Before.\n\n| a | b |\n| :- | :- |\n| one | two |\n\nAfter.\n",
			),
		).toBe(2);
	});

	test("drops directive markers and the wrapper the expander adds", () => {
		const source =
			':::callout type=info\n<div data-qgis-sdk="callout">\n<Callout type="info">\nBody.\n</Callout>\n</div>\n:::\n';
		expect(proseWords(source)).toBe(1);
	});

	test("drops a generated TypeTable, whose rows are a lookup", () => {
		const source =
			'Before.\n\n<div data-qgis-sdk="typetable">\n<TypeTable type={{\n"Thing": { type: "(x: int) -> None", description: "Tier `stable`." },\n"Other": { type: "class", description: "Tier `stable`." }\n}} />\n</div>\n\nAfter.\n';
		expect(proseWords(source)).toBe(2);
	});

	test("keeps headings, which are prose a reader reads", () => {
		expect(proseWords("## How do I name a job?\n")).toBe(6);
	});

	test("counts a hyphenated word once", () => {
		expect(proseWords("A worker-first runtime.\n")).toBe(3);
	});

	test("counts nothing in a page that is only code", () => {
		expect(proseWords("```sh\nqgis-sdk new demo\n```\n")).toBe(0);
	});
});

describe("proseOf", () => {
	test("returns the lines the count reads, so a reviewer can see them", () => {
		expect(
			proseOf("---\ntitle: A\n---\nText.\n\n```\ncode\n```\n").trim(),
		).toBe("Text.");
	});
});

describe("headingCount", () => {
	test("counts the headings a conversion turned into panels", () => {
		expect(headingCount("## One\n\n### Two\n\nText.\n")).toBe(2);
	});

	test("does not mistake a heading inside a fence for a heading", () => {
		expect(headingCount("```md\n## Not a heading\n```\n")).toBe(0);
	});
});
