/**
 * The AI-facing half of the site: `llms.txt`, `llms-full.txt` and one `.md`
 * per page, written into the exported site after the Next build.
 *
 * They are files, not routes, because GitHub Pages serves files: an agent
 * that can read `https://.../python/installation.md` needs no server, no
 * rewrites and no JavaScript. The same pass verifies the surface composes -
 * every page the site publishes has its markdown and every page is listed -
 * so a page added without an export fails the build rather than disappearing
 * from the index silently.
 */
import { access, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { ContentPage, ContentSection } from "./content";

export interface LlmsOptions {
	readonly site: string;
	readonly base: string;
	readonly title: string;
	readonly description: string;
	readonly repository: string;
}

/** Absolute URL of a page on the built site. */
function absolute(options: LlmsOptions, url: string): string {
	return `${options.site}${options.base}${url === "/" ? "/" : `${url}/`}`;
}

/** Absolute URL of a page's markdown export. */
function markdownUrl(options: LlmsOptions, url: string): string {
	return `${options.site}${options.base}${url === "/" ? "/index" : url}.md`;
}

/** `llms.txt`: the index an agent reads first. */
export function renderIndex(
	sections: readonly ContentSection[],
	options: LlmsOptions,
): string {
	const lines = [
		`# ${options.title}`,
		"",
		`> ${options.description}`,
		"",
		`Every page is also served as markdown: replace the trailing slash with \`.md\`.`,
		`\`llms-full.txt\` carries the whole documentation in one file.`,
		"",
	];
	for (const section of sections) {
		lines.push(`## ${section.label}`, "");
		for (const page of section.pages) {
			const summary = page.description ? `: ${page.description}` : "";
			lines.push(
				`- [${page.title}](${markdownUrl(options, page.url)})${summary}`,
			);
		}
		lines.push("");
	}
	lines.push("## Optional", "");
	lines.push(
		`- [Repository](${options.repository}): source, issues and releases.`,
		"",
	);
	return lines.join("\n");
}

/** `llms-full.txt`: every page, in sidebar order, with its source URL. */
export function renderFull(
	sections: readonly ContentSection[],
	options: LlmsOptions,
): string {
	const parts = [`# ${options.title}`, "", `> ${options.description}`, ""];
	for (const section of sections) {
		for (const page of section.pages) {
			parts.push(
				`# ${page.title}`,
				"",
				`Source: ${absolute(options, page.url)}`,
				"",
				page.body,
				"",
			);
		}
	}
	return parts.join("\n");
}

/** One page as standalone markdown: its title, then its prose. */
export function renderPage(page: ContentPage): string {
	return `# ${page.title}\n\n${page.body}\n`;
}

/**
 * Write the exports. A page's markdown file sits beside the page in the
 * export, so `/python/installation/` has `/python/installation.md`.
 */
export async function writeLlmsExports(
	out: string,
	sections: readonly ContentSection[],
	options: LlmsOptions,
): Promise<number> {
	let written = 0;
	for (const section of sections) {
		for (const page of section.pages) {
			if (page.url === "/") {
				continue;
			}
			const target = join(out, `${page.url}.md`);
			await mkdir(dirname(target), { recursive: true });
			await writeFile(target, renderPage(page));
			written += 1;
		}
	}
	await writeFile(join(out, "llms.txt"), renderIndex(sections, options));
	await writeFile(join(out, "llms-full.txt"), renderFull(sections, options));
	return written;
}

/** Every route the exported site publishes, as site paths (`/python`). */
export async function publishedRoutes(out: string): Promise<string[]> {
	const routes: string[] = [];
	const visit = async (directory: string, prefix: string): Promise<void> => {
		for (const entry of await readdir(directory, { withFileTypes: true })) {
			const path = join(directory, entry.name);
			const url = `${prefix}/${entry.name}`;
			if (entry.isDirectory()) {
				// The Storybook is a static app of its own, outside the docs.
				if (
					prefix === "" &&
					(entry.name === "_next" || entry.name === "storybook")
				) {
					continue;
				}
				if (entry.name === "404" || entry.name === "_not-found") {
					continue;
				}
				await visit(path, url);
			} else if (entry.name === "index.html" && prefix !== "") {
				routes.push(prefix);
			}
		}
	};
	routes.push("/");
	await visit(out, "");
	return routes.sort();
}

export interface LlmsReport {
	readonly routes: number;
	readonly markdown: number;
	readonly broken: readonly string[];
}

/**
 * The completeness gate: every published page has a `.md` export and is
 * listed in `llms.txt`, and every page in the collection has a rendered page.
 * Returns what it found; the caller decides what a failure means.
 */
export async function verifyLlms(
	out: string,
	pages: readonly ContentPage[],
	routes: readonly string[],
	options: LlmsOptions,
): Promise<LlmsReport> {
	const index = await readFile(join(out, "llms.txt"), "utf8");
	const full = await readFile(join(out, "llms-full.txt"), "utf8");
	const broken: string[] = [];
	for (const route of routes) {
		if (route === "/") {
			continue;
		}
		try {
			await access(join(out, `${route}.md`));
		} catch {
			broken.push(`no markdown export for ${route}`);
		}
		if (!index.includes(markdownUrl(options, route))) {
			broken.push(`${route} is missing from llms.txt`);
		}
		if (!full.includes(`Source: ${absolute(options, route)}`)) {
			broken.push(`${route} is missing from llms-full.txt`);
		}
	}
	for (const page of pages) {
		if (page.url === "/") {
			continue;
		}
		if (!routes.includes(page.url)) {
			broken.push(`${page.url} has content but no page`);
		}
	}
	return { routes: routes.length, markdown: pages.length, broken };
}
