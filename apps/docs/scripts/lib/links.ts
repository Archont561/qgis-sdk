/**
 * Check every internal link of a built site (TASK-43 AC 1: "working internal
 * links"). Zero dependencies: Bun's HTMLRewriter reads `href` and `src`, the
 * file system answers whether the target exists, and the target page's ids
 * answer whether a fragment does. External links are not fetched; the site
 * has no network at build time and GitHub URLs are stable.
 *
 * Pure with respect to `dist`: the CLI in `../check-links.ts` picks the
 * directory and the exit code.
 */
import { existsSync } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import { join, posix, relative } from "node:path";

export interface BrokenLink {
	readonly page: string;
	readonly href: string;
	readonly reason: string;
}

export interface LinkReport {
	readonly pages: number;
	readonly checked: number;
	readonly broken: readonly BrokenLink[];
}

interface Options {
	readonly base: string;
}

async function htmlFiles(dir: string): Promise<string[]> {
	const out: string[] = [];
	for (const entry of await readdir(dir, { withFileTypes: true })) {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) {
			out.push(...(await htmlFiles(path)));
		} else if (entry.name.endsWith(".html")) {
			out.push(path);
		}
	}
	return out.sort();
}

interface Extracted {
	readonly links: string[];
	readonly ids: Set<string>;
}

function extract(html: string): Extracted {
	const links: string[] = [];
	const ids = new Set<string>();
	new HTMLRewriter()
		.on("[href]", {
			element(el) {
				const href = el.getAttribute("href");
				if (href !== null) {
					links.push(href);
				}
			},
		})
		.on("[src]", {
			element(el) {
				const src = el.getAttribute("src");
				if (src !== null) {
					links.push(src);
				}
			},
		})
		.on("[id]", {
			element(el) {
				const id = el.getAttribute("id");
				if (id !== null) {
					ids.add(id);
				}
			},
		})
		.transform(html);
	return { links, ids };
}

/** The file a site path resolves to under `dist`, or `null` when nothing is there. */
async function resolveFile(
	dist: string,
	sitePath: string,
): Promise<string | null> {
	const candidates = sitePath.endsWith("/")
		? [`${sitePath}index.html`]
		: [sitePath, `${sitePath}/index.html`, `${sitePath}.html`];
	for (const candidate of candidates) {
		const file = join(dist, candidate);
		if (existsSync(file) && (await stat(file)).isFile()) {
			return relative(dist, file);
		}
	}
	return null;
}

export async function checkLinks(
	dist: string,
	options: Options,
): Promise<LinkReport> {
	const base = options.base.endsWith("/") ? options.base : `${options.base}/`;
	const files = await htmlFiles(dist);
	const pages = new Map<string, Extracted>();
	for (const file of files) {
		pages.set(relative(dist, file), extract(await readFile(file, "utf8")));
	}
	const idsOf = async (file: string): Promise<Set<string>> => {
		const known = pages.get(file);
		if (known) {
			return known.ids;
		}
		return extract(await readFile(join(dist, file), "utf8")).ids;
	};

	const broken: BrokenLink[] = [];
	let checked = 0;
	for (const [page, { links, ids }] of pages) {
		const pageDir = posix.dirname(`/${page}`);
		for (const href of links) {
			if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//")) {
				continue; // external
			}
			checked += 1;
			const [pathAndQuery, fragment] = href.split("#", 2);
			const pathPart = pathAndQuery?.split("?", 1)[0] ?? "";
			if (pathPart === "") {
				if (fragment && !ids.has(decodeURIComponent(fragment))) {
					broken.push({
						page,
						href,
						reason: `missing fragment #${fragment} in ${page}`,
					});
				}
				continue;
			}
			const decoded = decodeURIComponent(pathPart ?? "");
			let sitePath: string;
			if (decoded.startsWith("/")) {
				if (!decoded.startsWith(base) && decoded !== base.slice(0, -1)) {
					broken.push({ page, href, reason: `outside base ${base}` });
					continue;
				}
				sitePath = decoded.slice(base.length - 1);
			} else {
				const resolved = posix.normalize(posix.join(pageDir, decoded));
				sitePath = resolved.startsWith(base)
					? resolved.slice(base.length - 1)
					: resolved.startsWith("/")
						? resolved
						: `/${resolved}`;
				if (decoded.endsWith("/") && !sitePath.endsWith("/")) {
					sitePath = `${sitePath}/`;
				}
			}
			const file = await resolveFile(dist, sitePath);
			if (file === null) {
				const expected = sitePath.endsWith("/")
					? `${sitePath}index.html`
					: sitePath;
				broken.push({
					page,
					href,
					reason: `no such file ${expected.replace(/^\//, "")}`,
				});
				continue;
			}
			if (fragment && file.endsWith(".html")) {
				const targetIds = await idsOf(file);
				if (!targetIds.has(decodeURIComponent(fragment))) {
					broken.push({
						page,
						href,
						reason: `missing fragment #${fragment} in ${file}`,
					});
				}
			}
		}
	}
	return { pages: pages.size, checked, broken };
}
