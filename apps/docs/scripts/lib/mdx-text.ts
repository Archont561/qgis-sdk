/**
 * Make guide prose legal MDX without changing what a reader sees.
 *
 * The guides are written as GitHub-flavoured markdown, where four things are
 * ordinary text and in MDX are syntax:
 *
 * - `{` and `}` open and close a JavaScript expression. A signature written in
 *   a code span (`createBridgeHarness(schema, { granted: [...] })`) is fine on
 *   one line and fatal when the span wraps, because MDX evaluates what it finds
 *   in the braces and `granted: [...]` is not a JavaScript expression.
 * - `<!-- ... -->` is a comment, and MDX reserves `<!` for what follows it. The
 *   support matrix in doc-12 is delimited by two such markers.
 * - `<https://example.com>` is an autolink in markdown and a tag in MDX.
 * - `>=0.10.0,<0.11` - a version range in a support table - opens a tag MDX
 *   cannot parse.
 *
 * Each is rewritten to the equivalent MDX spelling - `\{`, nothing, a markdown
 * link, `\<` - so the page renders what GitHub shows. The rewrite runs on text
 * only: fenced code is the caller's to exclude, and inline code spans are left
 * alone, because a backslash inside a code span is a backslash.
 *
 * One case needs more than an escape. MDX does **not** protect a code span that
 * crosses a line break: `` `qgis-sdk-runtime<0.10, `` continued on the next
 * line fails the build at the `<`, where markdown renders it as code. The span
 * is joined onto one line first, which is what markdown was already doing -
 * CommonMark turns the line ending inside a code span into a space.
 */

/** A bare autolink: a scheme, then anything but a space or `>`. */
const AUTOLINK = /<([a-z][a-z0-9+.-]*:[^>\s]+)>/g;
const COMMENT = /<!--[\s\S]*?-->/g;
const RUNS = /`+/g;

/** Escape what MDX reads as syntax and markdown reads as text. */
function escapeOutsideCode(text: string): string {
	return text
		.replace(/[{}]/g, (brace) => `\\${brace}`)
		.replace(/<(?![A-Za-z/!])/g, "\\<");
}

/**
 * Escape one line, leaving the inside of a code span alone.
 *
 * A line whose last backtick run has no partner cannot open a span that MDX
 * would honour, so its text is escaped like any other: that is the case
 * `joinWrappedCodeSpans` did not manage to join, and a stray backslash in the
 * output is better than a page that will not build.
 */
function escapeLine(line: string): string {
	const runs = [...line.matchAll(RUNS)];
	const loneLast = runs.length % 2 === 1;
	const out: string[] = [];
	let cursor = 0;
	let inCode = false;
	for (const [index, run] of runs.entries()) {
		const start = run.index;
		const text = line.slice(cursor, start);
		out.push(inCode ? text : escapeOutsideCode(text), run[0]);
		cursor = start + run[0].length;
		if (loneLast === false || index < runs.length - 1) inCode = !inCode;
	}
	const tail = line.slice(cursor);
	out.push(inCode ? tail : escapeOutsideCode(tail));
	return out.join("");
}

/** The length of the backtick run that opens a span and never closes, or 0. */
function openRun(line: string): number {
	const runs = [...line.matchAll(RUNS)];
	if (runs.length % 2 === 0) return 0;
	return (runs[runs.length - 1] as RegExpMatchArray)[0].length;
}

/** Join a code span the author wrapped onto a second line, as markdown would. */
function joinWrappedCodeSpans(markdown: string): string {
	const out: string[] = [];
	let pending: { lines: string[]; run: number } | null = null;
	for (const line of markdown.split("\n")) {
		if (pending === null) {
			const run = openRun(line);
			if (run === 0) {
				out.push(line);
				continue;
			}
			pending = { lines: [line], run };
			continue;
		}
		pending.lines.push(line);
		const joined = pending.lines
			.map((part, index) => (index === 0 ? part.trimEnd() : part.trim()))
			.join(" ");
		const closers = [...joined.matchAll(RUNS)].slice(1);
		if (closers.some((match) => match[0].length === pending?.run) === false) {
			continue;
		}
		out.push(joined);
		pending = null;
	}
	// A span nobody closed is left exactly as it was: joining it would append
	// the lines that follow, and the sanitizer is not in the business of
	// repairing prose it does not understand.
	if (pending !== null) out.push(...pending.lines);
	return out.join("\n");
}

/**
 * Rewrite a prose segment so MDX renders what markdown would.
 *
 * Call it on text outside fences; the caller already knows where the fences
 * are, and running this over a code block would edit the code.
 */
export function escapeMdx(markdown: string): string {
	return joinWrappedCodeSpans(markdown.replace(COMMENT, ""))
		.replace(AUTOLINK, (_whole, url: string) => `[${url}](${url})`)
		.split("\n")
		.map(escapeLine)
		.join("\n");
}
