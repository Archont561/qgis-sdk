/**
 * Render the backlog guides into Starlight pages.
 *
 * decision-29 made `backlog/docs/guides/doc-12`, `doc-13` and `doc-14` the
 * reference prose and kept every README minimal; the site is where that prose
 * is read. Nothing here is hand-maintained: each guide is split into one page
 * per `##` section under a directory of its own, the preamble becomes that
 * directory's index, sub-headings move up one level so the page title is the
 * only H1, and the links the guides write for the backlog are rewritten -
 * same-guide and cross-guide anchors to the routes that now hold them, every
 * other backlog record (decisions, tasks, plans) to the repository on GitHub.
 *
 * Pure functions only: the CLI in `../generate.ts` does the file system work.
 */
import { posix } from "node:path";

export interface Guide {
	/** The backlog document id, e.g. `doc-12`. */
	readonly id: string;
	/** The file name under `backlog/docs/guides/`. */
	readonly file: string;
	/** The site directory the guide renders into, e.g. `python`. */
	readonly section: string;
	/** The sidebar group label. */
	readonly label: string;
}

/** The three guides decision-29 named, in the order the sidebar shows them. */
export const GUIDES: readonly Guide[] = [
	{
		id: "doc-12",
		file: "doc-12 - qgis-sdk-Python-package-guide.md",
		section: "python",
		label: "Python package",
	},
	{
		id: "doc-13",
		file: "doc-13 - qgis-sdk-TypeScript-package-guide.md",
		section: "typescript",
		label: "TypeScript SDK",
	},
	{
		id: "doc-14",
		file: "doc-14 - Workspace-development-qualification-harnesses-and-evidence.md",
		section: "workspace",
		label: "Workspace and qualification",
	},
];

export interface Section {
	readonly heading: string;
	readonly slug: string;
	readonly body: string;
}

export interface AnchorTarget {
	/** The section page slug holding the heading. */
	readonly page: string;
	/** The heading id on that page, or `null` when the heading is the page itself. */
	readonly anchor: string | null;
}

export interface SplitGuide {
	readonly title: string;
	readonly intro: string;
	readonly sections: readonly Section[];
	/** Every heading slug of the guide, at any level, to the page that holds it. */
	readonly anchors: ReadonlyMap<string, AnchorTarget>;
}

export interface GuideInput {
	readonly guide: Guide;
	readonly markdown: string;
	/** An ISO date for Starlight's `lastUpdated`, when the caller knows it. */
	readonly lastUpdated?: string;
}

export interface RenderOptions {
	/** Astro's `base`, with a leading and no trailing slash (`/qgis-sdk`), or `""`. */
	readonly base: string;
	/** The repository URL backlog records link to. */
	readonly repository: string;
	/** The git ref `repository` links use. Default `main`. */
	readonly ref?: string;
}

export interface Page {
	/** Relative to the content directory, e.g. `python/installation.md`. */
	readonly path: string;
	readonly content: string;
}

export interface RenderWarning {
	readonly guide: string;
	readonly page: string;
	readonly link: string;
	readonly reason: string;
}

const GUIDES_DIR = "backlog/docs/guides";

/** GitHub's heading anchor: lower-case, punctuation dropped, spaces to hyphens. */
export function slugify(heading: string): string {
	return heading
		.toLowerCase()
		.replace(/[^\p{L}\p{N}\s-]/gu, "")
		.trim()
		.replace(/\s+/g, "-");
}

/** Split markdown into prose and fenced-code segments, so code is never rewritten. */
function segments(markdown: string): { code: boolean; text: string }[] {
	const out: { code: boolean; text: string }[] = [];
	let fence: string | null = null;
	let buffer: string[] = [];
	let code = false;
	const flush = () => {
		if (buffer.length > 0) {
			out.push({ code, text: buffer.join("\n") });
		}
		buffer = [];
	};
	for (const line of markdown.split("\n")) {
		const opening = /^\s*(`{3,}|~{3,})/.exec(line);
		if (fence === null && opening) {
			flush();
			code = true;
			fence = opening[1] ?? "```";
			buffer.push(line);
		} else if (fence !== null && line.trim().startsWith(fence)) {
			buffer.push(line);
			flush();
			code = false;
			fence = null;
		} else {
			buffer.push(line);
		}
	}
	flush();
	return out;
}

function stripFrontmatter(markdown: string): string {
	if (!markdown.startsWith("---\n")) {
		return markdown;
	}
	const end = markdown.indexOf("\n---\n", 4);
	return end === -1 ? markdown : markdown.slice(end + 5);
}

interface Heading {
	readonly level: number;
	readonly text: string;
}

function headingOf(line: string): Heading | null {
	const match = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
	return match
		? { level: (match[1] ?? "#").length, text: match[2] ?? "" }
		: null;
}

/** Split a guide into its title, preamble and `##` sections, and index its headings. */
export function splitGuide(markdown: string): SplitGuide {
	let title = "";
	const intro: string[] = [];
	const sections: { heading: string; slug: string; lines: string[] }[] = [];
	const anchors = new Map<string, AnchorTarget>();
	const seen = new Map<string, number>();
	const uniqueSlug = (text: string): string => {
		const slug = slugify(text);
		const count = seen.get(slug) ?? 0;
		seen.set(slug, count + 1);
		return count === 0 ? slug : `${slug}-${count}`;
	};

	for (const segment of segments(stripFrontmatter(markdown))) {
		for (const line of segment.text.split("\n")) {
			const heading = segment.code ? null : headingOf(line);
			const current = sections.at(-1);
			if (heading?.level === 1 && title === "") {
				title = heading.text;
				continue;
			}
			if (heading?.level === 2) {
				const slug = uniqueSlug(heading.text);
				sections.push({ heading: heading.text, slug, lines: [] });
				anchors.set(slug, { page: slug, anchor: null });
				continue;
			}
			if (heading && current) {
				const slug = uniqueSlug(heading.text);
				anchors.set(slug, { page: current.slug, anchor: slug });
			}
			(current ? current.lines : intro).push(line);
		}
	}
	return {
		title,
		intro: intro.join("\n").trim(),
		sections: sections.map((s) => ({
			heading: s.heading,
			slug: s.slug,
			body: s.lines.join("\n").trim(),
		})),
		anchors,
	};
}

/**
 * Markdown links, `[text](target)`; targets carry no spaces (the guides use
 * `%20`). The leading `!` of an image is captured so images are left alone.
 */
const LINK = /(!?)\[([^[\]]*)\]\(([^)\s]+)\)/g;

/**
 * Repository paths that are process, not product: the site never links them.
 * Official docs cite shipped artifacts (releases, registries, versions); how
 * the work was planned and tracked stays in the repository.
 */
const PROCESS_PATHS = [
	/^backlog\/tasks\//,
	/^backlog\/milestones\//,
	/^backlog\/docs\/plans\//,
	/^AGENTS\.md$/,
	/^\.agents\//,
];

/** Repository-relative path of a link written inside the guides directory. */
function repositoryPath(relative: string): string | null {
	const decoded = decodeURIComponent(relative.split("#", 2)[0] ?? "");
	const resolved = posix.normalize(posix.join(GUIDES_DIR, decoded));
	return resolved.startsWith("..") ? null : resolved;
}

function plainText(markdown: string): string {
	return markdown
		.replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
		.replace(/[`*_]/g, "")
		.replace(/\s+/g, " ")
		.trim();
}

/** The first prose paragraph, flattened and cut for a meta description. */
function describe(body: string, fallback: string): string {
	for (const segment of segments(body)) {
		if (segment.code) {
			continue;
		}
		const paragraph = segment.text
			.split(/\n\s*\n/)
			.map((p) => p.trim())
			.find(
				(p) =>
					p !== "" &&
					!p.startsWith("#") &&
					!p.startsWith("|") &&
					!p.startsWith("<"),
			);
		if (paragraph) {
			const text = plainText(paragraph);
			if (text.length <= 160) {
				return text;
			}
			const cut = text.slice(0, 157);
			return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), 80))}...`;
		}
	}
	return fallback;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** A section the guide itself marks as not released yet. */
const DRAFT_HEADING = /\((?:in progress|unreleased)\)/i;

/**
 * The caution a draft page opens with, or `null` for released content. The
 * notes of a line still being cut are published because the release needs
 * them, but they must not read as finished guidance.
 */
function draftNotice(heading: string): string | null {
	if (!DRAFT_HEADING.test(heading)) {
		return null;
	}
	const version = /\d+\.\d+\.\d+/.exec(heading)?.[0];
	const line = version
		? `the unreleased ${version} line`
		: "the unreleased next minor";
	return `:::caution[Draft]\nThese notes describe ${line}. Content changes as the release is cut.\n:::\n`;
}

function frontmatter(fields: Record<string, unknown>): string {
	const lines: string[] = ["---"];
	for (const [key, value] of Object.entries(fields)) {
		if (value === undefined) {
			continue;
		}
		if (typeof value === "object" && value !== null) {
			lines.push(`${key}:`);
			for (const [inner, innerValue] of Object.entries(value)) {
				lines.push(`  ${inner}: ${JSON.stringify(innerValue)}`);
			}
		} else if (typeof value === "string" && ISO_DATE.test(value)) {
			// Unquoted, so YAML reads a date: Starlight's `lastUpdated` wants one.
			lines.push(`${key}: ${value}`);
		} else {
			lines.push(`${key}: ${JSON.stringify(value)}`);
		}
	}
	lines.push("---", "");
	return lines.join("\n");
}

class Renderer {
	private readonly split = new Map<string, SplitGuide>();
	private readonly byId = new Map<string, Guide>();
	readonly warnings: RenderWarning[] = [];

	constructor(
		private readonly inputs: readonly GuideInput[],
		private readonly options: RenderOptions,
	) {
		for (const { guide, markdown } of inputs) {
			this.split.set(guide.id, splitGuide(markdown));
			this.byId.set(guide.id, guide);
		}
	}

	private route(guide: Guide, target: AnchorTarget | null): string {
		const dir = `${this.options.base}/${guide.section}/`;
		if (target === null) {
			return dir;
		}
		return `${dir}${target.page}/${target.anchor ? `#${target.anchor}` : ""}`;
	}

	private repositoryUrl(path: string, relative: string): string {
		const anchor = relative.split("#", 2)[1];
		const encoded = path.split("/").map(encodeURIComponent).join("/");
		const ref = this.options.ref ?? "main";
		return `${this.options.repository}/blob/${ref}/${encoded}${anchor ? `#${anchor}` : ""}`;
	}

	/**
	 * Where a link written inside `guide` points once the guide is split, or
	 * `null` when the site must not link it at all (the text is kept).
	 */
	private rewrite(
		guide: Guide,
		url: string,
		warn: (reason: string) => void,
	): string | null {
		if (/^[a-z][a-z0-9+.-]*:/i.test(url)) {
			return url;
		}
		let targetGuide: Guide | undefined;
		let anchor: string | null = null;
		if (url.startsWith("#")) {
			targetGuide = guide;
			anchor = url.slice(1);
		} else {
			const sibling = /^(doc-\d+)[^/#]*\.md(?:#(.*))?$/.exec(url);
			if (sibling && this.byId.has(sibling[1] ?? "")) {
				targetGuide = this.byId.get(sibling[1] ?? "");
				anchor = sibling[2] ?? null;
			}
		}
		if (targetGuide === undefined) {
			const path = repositoryPath(url);
			if (path === null) {
				warn("escapes the repository");
				return url;
			}
			if (PROCESS_PATHS.some((pattern) => pattern.test(path))) {
				warn("cites a process record; the link was dropped");
				return null;
			}
			return this.repositoryUrl(path, url);
		}
		if (anchor === null || anchor === "") {
			return this.route(targetGuide, null);
		}
		const target = this.split.get(targetGuide.id)?.anchors.get(anchor);
		if (target === undefined) {
			warn(`no heading #${anchor} in ${targetGuide.id}`);
			return url;
		}
		return this.route(targetGuide, target);
	}

	/** Rewrite links and demote headings in prose; leave fenced code untouched. */
	private prose(
		guide: Guide,
		page: string,
		body: string,
		demote: boolean,
	): string {
		return segments(body)
			.map((segment) => {
				if (segment.code) {
					return segment.text;
				}
				let text = segment.text.replace(
					LINK,
					(whole: string, image: string, label: string, url: string) => {
						if (image) {
							return whole;
						}
						const rewritten = this.rewrite(guide, url, (reason) =>
							this.warnings.push({ guide: guide.id, page, link: url, reason }),
						);
						return rewritten === null ? label : `[${label}](${rewritten})`;
					},
				);
				if (demote) {
					text = text.replace(/^#(#{2,5}\s)/gm, "$1");
				}
				return text;
			})
			.join("\n");
	}

	private editUrl(guide: Guide): string {
		const ref = this.options.ref ?? "main";
		const path = `${GUIDES_DIR}/${guide.file}`
			.split("/")
			.map(encodeURIComponent)
			.join("/");
		return `${this.options.repository}/edit/${ref}/${path}`;
	}

	render(): Page[] {
		const pages: Page[] = [];
		for (const { guide, lastUpdated } of this.inputs) {
			const split = this.split.get(guide.id);
			if (split === undefined) {
				continue;
			}
			const index = [
				this.prose(guide, "index", split.intro, false),
				"",
				"## Sections",
				"",
				...split.sections.map(
					(s) =>
						`- [${s.heading}](${this.route(guide, { page: s.slug, anchor: null })})`,
				),
				"",
			].join("\n");
			pages.push({
				path: `${guide.section}/index.md`,
				content:
					frontmatter({
						title: split.title,
						description: describe(split.intro, split.title),
						editUrl: this.editUrl(guide),
						lastUpdated,
						sidebar: { label: "Overview", order: 0 },
					}) + index,
			});
			split.sections.forEach((section, position) => {
				const draft = draftNotice(section.heading);
				const head = frontmatter({
					title: plainText(section.heading),
					description: describe(
						section.body,
						`${split.title}: ${plainText(section.heading)}`,
					),
					editUrl: this.editUrl(guide),
					lastUpdated,
					sidebar: {
						order: position + 1,
						...(draft ? { badge: { text: "Draft", variant: "caution" } } : {}),
					},
				});
				const body = this.prose(guide, section.slug, section.body, true);
				pages.push({
					path: `${guide.section}/${section.slug}.md`,
					content: `${head}${draft ? `${draft}\n` : ""}${body}\n`,
				});
			});
		}
		return pages;
	}
}

/** Render every guide; see the module comment for the rules. */
export function renderGuides(
	inputs: readonly GuideInput[],
	options: RenderOptions,
): Page[] & { warnings: RenderWarning[] } {
	const renderer = new Renderer(inputs, options);
	const pages = renderer.render();
	return Object.assign(pages, { warnings: renderer.warnings });
}
