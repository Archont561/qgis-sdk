/**
 * The component gate: what must be true of the rendered site before it ships.
 *
 * Two probe results, both on 2026-10-28, define the failure this module exists
 * to catch. A component in a `.mdx` page fails the build when it is not
 * registered (`Expected component Steps to be defined`), which is loud and
 * fine. The same component in a `.md` page is **dropped silently**: the build
 * stays green, the page ships, and the only trace is a paragraph where a pair
 * of steps should be. A rollout verified by "the build passed" therefore
 * proves nothing.
 *
 * So the gate asks the two questions a green build cannot:
 *
 * 1. **Does any `.md` page hold JSX?** If it does, that JSX is not rendered,
 *    and the page is wrong no matter what the build says.
 * 2. **Does every page that a directive gave a component to actually contain
 *    that component's marker in the exported HTML?** The generator records each
 *    page's directives in `lib/generated/components.json`; the expansion wraps
 *    every component in `<div data-qgis-sdk="name">`, so the marker is our own
 *    and does not depend on a Fumadocs class name that a minor release renames.
 *
 * Both checks are pure: the caller hands in the pages and a reader for the
 * exported HTML, so the same functions run in the tests with fixtures.
 */

/** A page that must be fixed before the site is published. */
export interface GateProblem {
	/** The page, as a reader would find it: content path or site route. */
	readonly where: string;
	readonly message: string;
}

/** The part of a content page the gate reads. */
export interface GatePage {
	/** Path under `content/docs`, e.g. `python/scoped-jobs.mdx`. */
	readonly source: string;
	/** The page body, frontmatter already removed. */
	readonly body: string;
}

/** A JSX element: an opening or closing tag whose name starts upper-case. */
const JSX = /<\/?([A-Z][A-Za-z0-9]*)(?:\s[^>]*)?\/?>/;

/**
 * Drop fenced blocks and inline code, where an angle bracket is notation.
 *
 * `BridgeSchema<O, S>`, `<LayerPicker>` and `<package>.plugin:<Class>` are all
 * real text in the guides; none of them is JSX, and a check that flagged them
 * would be switched off within a week. What is left after this is what the
 * renderer would treat as an element.
 */
export function stripCode(markdown: string): string {
	const kept: string[] = [];
	let fence: string | null = null;
	for (const line of markdown.split("\n")) {
		const trimmed = line.trim();
		if (fence !== null) {
			if (trimmed.startsWith(fence)) fence = null;
			kept.push("");
			continue;
		}
		const opened = /^(`{3,}|~{3,})/.exec(trimmed);
		if (opened !== null) {
			fence = opened[1] ?? "```";
			kept.push("");
			continue;
		}
		kept.push(line.replace(/`[^`]*`/g, ""));
	}
	return kept.join("\n");
}

/**
 * Every `.md` page that holds JSX, which the build would drop.
 *
 * A `.md` page is rendered as plain markdown: a component tag in one survives
 * as text, or vanishes with its wrapper, and nothing fails. The two file
 * extensions are one character apart and both are accepted by the collection,
 * so the check is the only thing standing between a typo and a page that
 * silently lost its content.
 */
export function jsxInMarkdown(
	pages: readonly GatePage[],
): readonly GateProblem[] {
	const problems: GateProblem[] = [];
	for (const page of pages) {
		if (page.source.endsWith(".md") === false) continue;
		for (const [index, line] of stripCode(page.body).split("\n").entries()) {
			const match = JSX.exec(line);
			if (match === null) continue;
			problems.push({
				where: `${page.source}:${index + 1}`,
				message:
					`<${match[1]}> is JSX in a .md page, which markdown drops; ` +
					"rename the page to .mdx or write a directive",
			});
			break;
		}
	}
	return problems;
}

/** Reads one exported page's HTML, or `null` when the route was not written. */
export type HtmlReader = (route: string) => Promise<string | null>;

/** The marker the directive expansion wraps a component in. */
export function markerOf(name: string): string {
	return `data-qgis-sdk="${name}"`;
}

/**
 * Every page whose recorded components are not all in its exported HTML.
 *
 * `use` is the generator's record - route to the directive names that expanded
 * into components - and it is the expectation, not the page's text: a page
 * that lost a component still contains its words, so only the marker can say
 * whether the component rendered.
 */
export async function missingComponentMarkup(
	use: Readonly<Record<string, readonly string[]>>,
	read: HtmlReader,
): Promise<readonly GateProblem[]> {
	const problems: GateProblem[] = [];
	for (const [route, names] of Object.entries(use)) {
		const html = await read(route);
		if (html === null) {
			problems.push({
				where: route,
				message: "carries components but was not exported; check the route",
			});
			continue;
		}
		for (const name of names) {
			if (html.includes(markerOf(name))) continue;
			problems.push({
				where: route,
				message:
					`:::${name} produced no ${markerOf(name)} in the page; ` +
					"the component was dropped instead of rendered",
			});
		}
	}
	return problems;
}
