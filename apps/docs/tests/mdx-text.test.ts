/**
 * The MDX sanitiser: markdown that GitHub renders as prose, and MDX as syntax.
 *
 * Every case here comes from a real guide page - the support matrix, a wrapped
 * code span, an autolink - and every one broke `next build` when the guides
 * became `.mdx`. The tests keep the rewrite honest in both directions: syntax
 * that would fail the build is escaped, and text that would fail it wrongly
 * (a code span, a comparison written as prose) is left alone.
 */
import { describe, expect, test } from "bun:test";
import { escapeMdx } from "../scripts/lib/mdx-text";

describe("escapeMdx", () => {
	test("leaves ordinary prose untouched", () => {
		const source = "A paragraph with a [link](/python) and *emphasis*.\n";
		expect(escapeMdx(source)).toBe(source);
	});

	test("removes an HTML comment, which MDX reserves", () => {
		expect(escapeMdx("<!-- support-matrix:begin -->\n\n| a | b |\n")).toBe(
			"\n\n| a | b |\n",
		);
	});

	test("escapes braces outside code so they stay text", () => {
		expect(escapeMdx("a {literal} brace\n")).toBe("a \\{literal\\} brace\n");
	});

	test("leaves a single-line code span alone", () => {
		const source =
			"Call `createBridgeHarness(schema, { granted: [] })` first.\n";
		expect(escapeMdx(source)).toBe(source);
	});

	test("joins a code span the author wrapped, as markdown would", () => {
		const source =
			"the tools' `qgis-sdk-runtime<0.10,\n  >=0.9.0`; from those wheels\n";
		expect(escapeMdx(source)).toBe(
			"the tools' `qgis-sdk-runtime<0.10, >=0.9.0`; from those wheels\n",
		);
	});

	test("escapes a wrapped span holding braces by joining it first", () => {
		const source = '`createBridgeHarness(schema,\n  { granted: ["x"] })`\n';
		expect(escapeMdx(source)).toBe(
			'`createBridgeHarness(schema, { granted: ["x"] })`\n',
		);
	});

	test("escapes a comparison, which MDX reads as a tag", () => {
		expect(escapeMdx("requires >=0.10.0,<0.11 of the runtime\n")).toBe(
			"requires >=0.10.0,\\<0.11 of the runtime\n",
		);
	});

	test("turns an autolink into a link", () => {
		expect(escapeMdx("see <https://example.com> for more\n")).toBe(
			"see [https://example.com](https://example.com) for more\n",
		);
	});

	test("leaves an ordinary tag-looking name in a code span", () => {
		const source = "- **Schema types:** `BridgeSchema<O, S>` and friends\n";
		expect(escapeMdx(source)).toBe(source);
	});

	test("escapes braces after an unpaired backtick rather than trusting it", () => {
		expect(escapeMdx("a stray ` tick and {braces}\n")).toBe(
			"a stray ` tick and \\{braces\\}\n",
		);
	});
});
