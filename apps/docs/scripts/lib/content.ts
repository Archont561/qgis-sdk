/**
 * The content collection, as the post-build export needs it: one record per
 * page, in the order the sidebar shows.
 *
 * The site is rendered by Next, which knows the pages but not their markdown.
 * These readers answer the other half - the title and description frontmatter
 * carry and the prose itself - so `llms.txt`, `llms-full.txt` and the
 * per-page `.md` files can be written from the same source the pages were
 * built from, with no second copy of the prose in git.
 */
import { readdir, readFile } from "node:fs/promises";
import { join, posix, relative } from "node:path";

export interface ContentPage {
	/** Site path with a leading slash and no trailing one, e.g. `/python`. */
	readonly url: string;
	readonly title: string;
	readonly description?: string;
	/** The page body without its frontmatter. */
	readonly body: string;
	/** Directory under `content/docs` holding the page, `.` for the root. */
	readonly section: string;
}

interface Frontmatter {
	readonly title: string;
	readonly description?: string;
	readonly body: string;
}

const FRONTMATTER = /^---\n([\s\S]*?)\n---(?:\n|$)/;

function unquote(value: string): string {
	const quoted = /^(['"])([\s\S]*)\1$/.exec(value);
	return quoted?.[2] ?? value;
}

/** Split a page into its frontmatter fields and its body. */
export function parsePage(
	markdown: string,
	fallbackTitle: string,
): Frontmatter {
	const match = FRONTMATTER.exec(markdown);
	const fields = new Map<string, string>();
	if (match) {
		for (const line of (match[1] ?? "").split("\n")) {
			const pair = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line);
			if (pair) {
				fields.set(pair[1] ?? "", unquote((pair[2] ?? "").trim()));
			}
		}
	}
	const title = fields.get("title") ?? fallbackTitle;
	const description = fields.get("description");
	return {
		title,
		...(description === undefined || description === "" ? {} : { description }),
		body: match ? markdown.slice(match[0].length) : markdown,
	};
}

/** Read a folder's `meta.json`, or an empty one when it has none. */
async function readMeta(
	directory: string,
): Promise<{ title?: string; pages?: string[] }> {
	try {
		return JSON.parse(await readFile(join(directory, "meta.json"), "utf8")) as {
			title?: string;
			pages?: string[];
		};
	} catch {
		return {};
	}
}

/**
 * Every page of the collection, in `meta.json` order within a folder: a
 * folder's own pages first (index, then what its `pages` names), then its
 * subfolders.
 */
export async function collectPages(
	contentDir: string,
): Promise<readonly ContentPage[]> {
	const pages: ContentPage[] = [];
	const visit = async (directory: string): Promise<void> => {
		const meta = await readMeta(directory);
		const entries = await readdir(directory, { withFileTypes: true });
		const order = meta.pages ?? [];
		const stem = (name: string): string => name.replace(/\.mdx?$/, "");
		const rank = (name: string): number => {
			const index = order.indexOf(stem(name));
			return index === -1 ? order.length : index;
		};
		const files = entries
			.filter((entry) => entry.isFile() && /\.mdx?$/.test(entry.name))
			.map((entry) => entry.name)
			.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
		for (const name of files) {
			const path = join(directory, name);
			const slug = relative(contentDir, path)
				.split("\\")
				.join("/")
				.replace(/\.mdx?$/, "")
				.replace(/(^|\/)index$/, "");
			const { title, description, body } = parsePage(
				await readFile(path, "utf8"),
				slug === "" ? "Overview" : (slug.split("/").at(-1) ?? slug),
			);
			const section = posix.dirname(
				relative(contentDir, path).split("\\").join("/"),
			);
			pages.push({
				url: slug === "" ? "/" : `/${slug}`,
				title,
				...(description === undefined ? {} : { description }),
				body: body.trim(),
				section: section === "" ? "." : section,
			});
		}
		const folders = entries
			.filter((entry) => entry.isDirectory())
			.map((entry) => entry.name)
			.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
		for (const folder of folders) {
			await visit(join(directory, folder));
		}
	};
	await visit(contentDir);
	return pages;
}

/** A top-level section of the sidebar: its label and the pages inside it. */
export interface ContentSection {
	readonly label: string;
	readonly pages: readonly ContentPage[];
}

/**
 * Group the collection the way the sidebar shows it: root pages first, then
 * one group per top-level folder, labelled by that folder's `meta.json`.
 */
export function sectionPages(
	pages: readonly ContentPage[],
	labels: Readonly<Record<string, string>>,
): readonly ContentSection[] {
	const root: ContentPage[] = [];
	const groups = new Map<string, ContentPage[]>();
	for (const page of pages) {
		const [first] = page.section.split("/");
		if (first === undefined || first === ".") {
			root.push(page);
			continue;
		}
		groups.set(first, [...(groups.get(first) ?? []), page]);
	}
	return [
		...(root.length > 0 ? [{ label: "Overview", pages: root }] : []),
		...[...groups.entries()].map(([key, group]) => ({
			label: labels[key] ?? key,
			pages: group,
		})),
	];
}

/** The labels the root `meta.json` and each folder's own carry. */
export async function sectionLabels(
	contentDir: string,
): Promise<Readonly<Record<string, string>>> {
	const root = await readMeta(contentDir);
	const labels: Record<string, string> = {};
	for (const key of root.pages ?? []) {
		if (key.includes("/")) {
			continue;
		}
		labels[key] = (await readMeta(join(contentDir, key))).title ?? key;
	}
	return labels;
}
