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
 *    route still redirects to a page that exists, and no compatibility page
 *    leaks into the sitemap or the llms index.
 */

import { fileURLToPath } from "node:url";
import { BASE, DESCRIPTION, REPOSITORY, SITE, TITLE } from "../site";
import { collectPages, sectionLabels, sectionPages } from "./lib/content";
import { publishedRoutes, verifyLlms, writeLlmsExports } from "./lib/llms";
import {
	LEGACY_ROUTES,
	verifyRedirectSurfaces,
	writeRedirects,
} from "./lib/redirects";
import { writeSitemap } from "./lib/sitemap";

const DOCS = fileURLToPath(new URL("..", import.meta.url));
const OUT = `${DOCS}/out`;
const CONTENT = `${DOCS}/content/docs`;

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
if (report.broken.length > 0) {
	process.exit(1);
}
