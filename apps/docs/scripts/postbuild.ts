/**
 * Everything the exported site needs beyond the rendered pages, run after
 * `next build` against `out/`:
 *
 * 1. `llms.txt`, `llms-full.txt` and one `.md` per page - the AI-facing
 *    surface, written as files because GitHub Pages serves files;
 * 2. `sitemap-index.xml` and `sitemap-0.xml` for the routes that were
 *    rendered;
 * 3. the compatibility pages for routes published before the guides were
 *    reorganised;
 * 4. the checks: every page has its markdown and is listed, every legacy
 *    route still redirects to a page that exists, no compatibility page
 *    leaks into the sitemap or the llms index, no `.md` page holds JSX that
 *    the build dropped, every page a directive gave a component to carries
 *    that component in the exported HTML, and every page holds its prose
 *    allowance exactly (the ratchet, decision-86 item 2).
 */

import { fileURLToPath } from "node:url";
import { BASE, DESCRIPTION, REPOSITORY, SITE, TITLE } from "../site";
import { collectPages, sectionLabels, sectionPages } from "./lib/content";
import {
	type GateProblem,
	type HtmlReader,
	jsxInMarkdown,
	missingComponentMarkup,
} from "./lib/gate";
import { publishedRoutes, verifyLlms, writeLlmsExports } from "./lib/llms";
import { ratchetProblems } from "./lib/ratchet";
import {
	LEGACY_ROUTES,
	verifyRedirectSurfaces,
	writeRedirects,
} from "./lib/redirects";
import { writeSitemap } from "./lib/sitemap";

const DOCS = fileURLToPath(new URL("..", import.meta.url));
const OUT = `${DOCS}/out`;
const CONTENT = `${DOCS}/content/docs`;
const COMPONENT_USE = `${DOCS}/lib/generated/components.json`;
const PROSE_BUDGET = `${DOCS}/prose-budget.json`;

/** The generator's record of which pages carry which directive components. */
async function componentUse(): Promise<
	Readonly<Record<string, readonly string[]>>
> {
	try {
		return JSON.parse(await Bun.file(COMPONENT_USE).text()) as Record<
			string,
			readonly string[]
		>;
	} catch {
		// No record means no page carries a directive; the generator always
		// writes the file, so this only happens for a hand-run postbuild.
		return {};
	}
}

/** The exported HTML of a route, or `null` when the route was not written. */
const htmlOf: HtmlReader = async (route) => {
	const path = `${OUT}${route === "/" ? "" : route}/index.html`;
	const file = Bun.file(path);
	return (await file.exists()) ? await file.text() : null;
};

const pages = await collectPages(CONTENT);
const sections = sectionPages(pages, await sectionLabels(CONTENT));
const options = {
	site: SITE,
	base: BASE,
	title: TITLE,
	description: DESCRIPTION,
	repository: REPOSITORY,
};

const markdown = await writeLlmsExports(OUT, sections, options);
console.log(
	`postbuild: ${markdown} markdown exports, llms.txt and llms-full.txt`,
);

// The compatibility pages are ours, not routes: a rebuild in place leaves the
// ones from the previous run on disk, and neither the sitemap nor the llms
// index may ever list a redirect.
const legacy = new Set(Object.keys(LEGACY_ROUTES));
const routes = (await publishedRoutes(OUT)).filter(
	(route) => !legacy.has(route.replace(/^\//, "")),
);
const sitemap = await writeSitemap(OUT, routes, { site: SITE, base: BASE });
console.log(`postbuild: sitemap with ${sitemap} routes`);

await writeRedirects(OUT, LEGACY_ROUTES);
await verifyRedirectSurfaces(OUT, LEGACY_ROUTES);
console.log(
	`postbuild: ${Object.keys(LEGACY_ROUTES).length} compatibility pages verified`,
);

const report = await verifyLlms(OUT, pages, routes, options);
for (const problem of report.broken) {
	console.error(`postbuild: ${problem}`);
}
console.log(
	`postbuild: ${report.routes} routes, ${report.markdown} pages, ${report.broken.length} unresolved`,
);
// The component gate: a `.md` page holding JSX, and a page whose directive
// produced no component, are both failures the build itself cannot see.
const use = await componentUse();
const problems: GateProblem[] = [
	...jsxInMarkdown(pages),
	...(await missingComponentMarkup(use, htmlOf)),
];
for (const problem of problems) {
	console.error(`postbuild: ${problem.where}: ${problem.message}`);
}
console.log(
	`postbuild: component gate over ${Object.keys(use).length} pages with directives, ${problems.length} problems`,
);
// The prose ratchet: a page that grew past its allowance, or fell under it
// without the allowance being lowered, fails the build (decision-86 item 2).
const ratchet = await ratchetProblems(CONTENT, PROSE_BUDGET);
for (const problem of ratchet) {
	console.error(`postbuild: ${problem.where}: ${problem.message}`);
}
console.log(`postbuild: prose ratchet, ${ratchet.length} problems`);
if (report.broken.length > 0 || problems.length > 0 || ratchet.length > 0) {
	process.exit(1);
}
