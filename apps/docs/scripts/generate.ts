/**
 * Write the generated half of `content/docs/` before `next build|dev`.
 *
 * - the three reference guides, one directory each plus a `migration/` folder
 *   for the migration notes (see `lib/guides.ts`);
 * - `reference/design-decisions.md`, one curated table over the decision
 *   records (see `lib/decisions.ts` and `decision-summaries.ts`);
 * - the `meta.json` files that give every generated folder its title and page
 *   order, so the sidebar is data rather than a hand-kept list in the layout;
 * - `lib/generated/` - the versions the site describes and, per page, the
 *   guide source it came from and when that source last changed;
 * - `public/storybook/`, a copy of `packages/qgis-sdk-ui/storybook-static`
 *   when it has been built, so the component Storybook ships with the site.
 *
 * All of it is ignored by git; the sources are the guides, the records, the
 * stories and the workspace manifests.
 */

import { existsSync } from "node:fs";
import { cp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { REPOSITORY } from "../site";
import { versions } from "../versions";
import { DECISION_SUMMARIES } from "./decision-summaries";
import { parseDecision, renderDecisionsPage } from "./lib/decisions";
import {
	GUIDES,
	type GuideInput,
	type Page,
	renderGuides,
	splitGuide,
} from "./lib/guides";

const DOCS_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(DOCS_DIR, "../../..");
const GUIDES_DIR = join(ROOT, "apps/docs/guides");
const DECISIONS_DIR = join(ROOT, "backlog/decisions");
const DECISIONS_PAGE = "reference/design-decisions.mdx";
const CONTENT_DIR = join(DOCS_DIR, "../content/docs");
const GENERATED_DIR = join(DOCS_DIR, "../lib/generated");
const STORYBOOK_SOURCE = join(ROOT, "packages/qgis-sdk-ui/storybook-static");
const STORYBOOK_TARGET = join(DOCS_DIR, "../public/storybook");

/** The guide whose section a page was rendered from, keyed by page path. */
interface PageSource {
	readonly edit: string;
	readonly lastUpdated?: string;
}

async function lastCommitDate(path: string): Promise<string | undefined> {
	const proc = Bun.spawn(
		["git", "log", "--follow", "-1", "--format=%cs", "--", path],
		{
			cwd: ROOT,
			stdout: "pipe",
			stderr: "ignore",
		},
	);
	const date = (await new Response(proc.stdout).text()).trim();
	return (await proc.exited) === 0 && date !== "" ? date : undefined;
}

/** The guide file, repository-relative: what "Edit this page" opens. */
function editPathOf(guide: (typeof GUIDES)[number]): string {
	return `apps/docs/guides/${guide.file}`;
}

/** `python/migration/v0-4.md` -> `python/migration`. */
function directoryOf(path: string): string {
	return dirname(path).split("\\").join("/");
}

async function writeJson(path: string, value: unknown): Promise<void> {
	await mkdir(dirname(path), { recursive: true });
	await writeFile(path, `${JSON.stringify(value, null, "\t")}\n`);
}

async function main(): Promise<void> {
	const inputs: GuideInput[] = [];
	const sources = new Map<string, PageSource>();
	for (const guide of GUIDES) {
		const path = join(GUIDES_DIR, guide.file);
		const markdown = await Bun.file(path).text();
		const lastUpdated = await lastCommitDate(path);
		inputs.push({ guide, markdown, lastUpdated });
		const split = splitGuide(markdown);
		for (const page of [
			`${guide.section}/index.md`,
			...split.sections.map((section) => `${guide.section}/${section.slug}.md`),
		]) {
			sources.set(`/${page.slice(0, -".md".length)}`, {
				edit: editPathOf(guide),
				...(lastUpdated === undefined ? {} : { lastUpdated }),
			});
		}
	}
	// Root-relative routes: the links Next renders carry the deployment's
	// basePath already, so prefixing it here would double it.
	const pages = renderGuides(inputs, { base: "", repository: REPOSITORY });

	// Every directory the guides render into is theirs alone, so a page whose
	// section was renamed or removed does not linger from an earlier run.
	for (const dir of new Set(pages.map((page) => directoryOf(page.path)))) {
		await rm(join(CONTENT_DIR, dir), { recursive: true, force: true });
	}
	for (const page of pages) {
		const target = join(CONTENT_DIR, page.path);
		await mkdir(dirname(target), { recursive: true });
		await writeFile(target, page.content);
	}
	for (const warning of pages.warnings) {
		console.warn(
			`generate: ${warning.guide}/${warning.page}: link ${warning.link} ${warning.reason}`,
		);
	}
	console.log(`generate: ${pages.length} pages from ${GUIDES.length} guides`);

	// The sidebar's shape: one `meta.json` per generated folder.
	const byDirectory = new Map<string, Page[]>();
	for (const page of pages) {
		const dir = directoryOf(page.path);
		byDirectory.set(dir, [...(byDirectory.get(dir) ?? []), page]);
	}
	for (const guide of GUIDES) {
		const entries = byDirectory.get(guide.section) ?? [];
		const order = [
			"index",
			...entries
				.filter((page) => page.order === undefined)
				.map((page) => page.path.slice(page.path.lastIndexOf("/") + 1))
				.filter((name) => name !== "index.md")
				.map((name) => name.replace(/\.md$/, "")),
			...(byDirectory.has(`${guide.section}/migration`) ? ["migration"] : []),
		];
		await writeJson(join(CONTENT_DIR, guide.section, "meta.json"), {
			title: guide.label,
			pages: order,
		});
		const migration = (byDirectory.get(`${guide.section}/migration`) ?? [])
			.slice()
			.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
			.map((page) => page.path.replace(/^.*\//, "").replace(/\.md$/, ""));
		if (migration.length > 0) {
			await writeJson(join(CONTENT_DIR, guide.section, "migration/meta.json"), {
				title: "Migration notes",
				pages: migration,
			});
		}
	}
	// A guide that renders into a nested directory (`contributing/workspace`)
	// still needs a title and an order for the folder above it.
	for (const guide of GUIDES) {
		const [first, ...rest] = guide.section.split("/");
		if (first !== undefined && rest.length > 0) {
			await writeJson(join(CONTENT_DIR, first, "meta.json"), {
				title: guide.label,
				pages: [rest.join("/")],
			});
		}
	}
	await writeJson(join(CONTENT_DIR, "reference/meta.json"), {
		title: "Reference",
		pages: ["design-decisions"],
	});

	const records = (await readdir(DECISIONS_DIR))
		.filter((name) => /^decision-\d+ .*\.md$/.test(name))
		.sort();
	const decisions = await Promise.all(
		records.map(async (name) =>
			parseDecision(name, await Bun.file(join(DECISIONS_DIR, name)).text()),
		),
	);
	const table = renderDecisionsPage(decisions, DECISION_SUMMARIES, {
		repository: REPOSITORY,
	});
	for (const number of table.missing) {
		console.warn(
			`generate: decision-${number} has no summary in scripts/decision-summaries.ts; its title stands in`,
		);
	}
	await rm(join(CONTENT_DIR, dirname(DECISIONS_PAGE)), {
		recursive: true,
		force: true,
	});
	await mkdir(join(CONTENT_DIR, dirname(DECISIONS_PAGE)), { recursive: true });
	await writeFile(join(CONTENT_DIR, DECISIONS_PAGE), table.content);
	console.log(`generate: ${DECISIONS_PAGE} from ${decisions.length} records`);

	// What the layout needs to know about pages it did not author: the version
	// badges, the edit link back to the guide, and the guide's last commit.
	await writeJson(join(GENERATED_DIR, "versions.json"), versions);
	const edits: Record<string, PageSource> = Object.fromEntries(
		[...sources.entries()].sort(([a], [b]) => a.localeCompare(b)),
	);
	await writeJson(join(GENERATED_DIR, "pages.json"), edits);

	await rm(STORYBOOK_TARGET, { recursive: true, force: true });
	if (existsSync(join(STORYBOOK_SOURCE, "index.html"))) {
		await cp(STORYBOOK_SOURCE, STORYBOOK_TARGET, { recursive: true });
		console.log("generate: storybook copied to public/storybook");
	} else {
		console.log("generate: no storybook-static build; /storybook/ is omitted");
	}
}

await main();
