/**
 * The heading anchor, in one place.
 *
 * GitHub's rule - lower-case, punctuation dropped, spaces to hyphens - is what
 * the guide sources' own links use, what `splitGuide` maps to routes, and what
 * an accordion's `id` has to carry once its heading becomes a panel: a heading
 * inside an accordion is no longer an `<h3>`, so the id on the accordion header
 * is the only thing keeping `#how-do-i-name-the-jobs` working.
 *
 * Two callers, one function: `guides.ts` for the routes it rewrites and
 * `directives.ts` for the ids it emits into an `:::accordion`. A second copy
 * would drift on the first heading with a question mark in it.
 */
export function slugify(heading: string): string {
	return heading
		.toLowerCase()
		.replace(/[^\p{L}\p{N}\s-]/gu, "")
		.trim()
		.replace(/\s+/g, "-");
}
