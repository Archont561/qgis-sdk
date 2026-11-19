/**
 * Count the prose words on a page, so "25 percent less text" is a number.
 *
 * What counts: the body after the frontmatter, fences removed, table rows
 * removed, directive markers and the JSX tags the expander writes removed. What
 * does not: code (its lines are the thing a reader copies, not reads), tables (a
 * row is a lookup, and moving a catalogue into a `:::files` tree or a `TypeTable`
 * is the point of the exercise), and the `data-qgis-sdk` wrappers the expander
 * adds.
 *
 * The definition is a choice, so it is written down and tested rather than
 * implied by whatever `wc -w` happens to do. A page measured before and after a
 * conversion is measured by the same function. The CLI that applies it to the
 * corpus is `scripts/measure-prose.ts`; this module is pure so the tests can pin
 * it without reading a directory.
 */

/** A word: letters, digits, and the apostrophe or hyphen inside one. */
const WORD = /[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu;
const FRONTMATTER = /^---\n[\s\S]*?\n---\n/;
const FENCE = /^\s*(?:```|~~~)/;
const TABLE_ROW = /^\s*\|/;
const MARKER = /^\s*:::/;
const WRAPPER = /^\s*<\/?div data-qgis-sdk/;
/** A JSX tag on a line of its own, which the expander emitted, not prose. */
const JSX_LINE = /^\s*<\/?[A-Za-z][^>]*>\s*$/;
const HEADING = /^\s{0,3}#{1,6}\s/;

/** The prose of a page, as the count defines it. */
export function proseOf(markdown: string): string {
	const body = markdown.replace(FRONTMATTER, "");
	const kept: string[] = [];
	let fence = false;
	for (const line of body.split("\n")) {
		if (FENCE.test(line)) {
			fence = !fence;
			continue;
		}
		if (fence) continue;
		if (
			TABLE_ROW.test(line) ||
			MARKER.test(line) ||
			WRAPPER.test(line) ||
			JSX_LINE.test(line)
		) {
			continue;
		}
		kept.push(line);
	}
	return kept.join("\n");
}

/** The count of prose words on a page. */
export function proseWords(markdown: string): number {
	return (proseOf(markdown).match(WORD) ?? []).length;
}

/** The count of headings a page still carries, so a conversion shows its cost. */
export function headingCount(markdown: string): number {
	return proseOf(markdown)
		.split("\n")
		.filter((line) => HEADING.test(line)).length;
}
