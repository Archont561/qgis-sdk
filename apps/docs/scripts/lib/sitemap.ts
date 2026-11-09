/**
 * The sitemap, written after the build.
 *
 * Astro's Starlight used to bundle `@astrojs/sitemap`, which is where
 * `sitemap-index.xml` and `sitemap-0.xml` came from; `public/robots.txt`
 * points at the index and the redirect check reads it, so the export keeps
 * both names and the same shape.
 */
import { writeFile } from "node:fs/promises";
import { join } from "node:path";

const HEADER = '<?xml version="1.0" encoding="UTF-8"?>';

/** Write `sitemap-index.xml` and `sitemap-0.xml` for `routes`. */
export async function writeSitemap(
	out: string,
	routes: readonly string[],
	options: { site: string; base: string },
): Promise<number> {
	const urls = routes
		.map(
			(route) =>
				`\t<url><loc>${options.site}${options.base}${route === "/" ? "/" : `${route}/`}</loc></url>`,
		)
		.join("\n");
	await writeFile(
		join(out, "sitemap-0.xml"),
		`${HEADER}\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
	);
	await writeFile(
		join(out, "sitemap-index.xml"),
		`${HEADER}\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n\t<sitemap><loc>${options.site}${options.base}/sitemap-0.xml</loc></sitemap>\n</sitemapindex>\n`,
	);
	return routes.length;
}
