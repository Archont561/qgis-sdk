/**
 * Write the generated half of `src/content/docs/` before `astro dev|build`.
 *
 * - the three backlog guides, one directory each plus a `<section>-migration`
 *   sibling for the migration notes (see `lib/guides.ts`);
 * - `reference/design-decisions.md`, one curated table over the decision
 *   records (see `lib/decisions.ts` and `decision-summaries.ts`);
 * - `public/storybook/`, a copy of `packages/qgis-sdk-ui/storybook-static`
 *   when it has been built, so the component Storybook ships with the site.
 *
 * All three outputs are ignored by git; the sources are the guides, the
 * records and the stories.
 * `lastUpdated` comes from the guide's last commit, so a page is as fresh as
 * the prose it renders rather than as the build that rendered it.
 */

import { existsSync } from "node:fs";
import { cp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { BASE, REPOSITORY } from "../site";
import { DECISION_SUMMARIES } from "./decision-summaries";
import { parseDecision, renderDecisionsPage } from "./lib/decisions";
import { GUIDES, type GuideInput, renderGuides } from "./lib/guides";

const DOCS_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(DOCS_DIR, "../../..");
const GUIDES_DIR = join(ROOT, "backlog/docs/guides");
const DECISIONS_DIR = join(ROOT, "backlog/decisions");
const DECISIONS_PAGE = "reference/design-decisions.md";
const CONTENT_DIR = join(DOCS_DIR, "../src/content/docs");
const STORYBOOK_SOURCE = join(ROOT, "packages/qgis-sdk-ui/storybook-static");
const STORYBOOK_TARGET = join(DOCS_DIR, "../public/storybook");

async function lastCommitDate(path: string): Promise<string | undefined> {
	const proc = Bun.spawn(["git", "log", "-1", "--format=%cs", "--", path], {
		cwd: ROOT,
		stdout: "pipe",
		stderr: "ignore",
	});
	const date = (await new Response(proc.stdout).text()).trim();
	return (await proc.exited) === 0 && date !== "" ? date : undefined;
}

async function main(): Promise<void> {
	const inputs: GuideInput[] = [];
	for (const guide of GUIDES) {
		const path = join(GUIDES_DIR, guide.file);
		inputs.push({
			guide,
			markdown: await Bun.file(path).text(),
			lastUpdated: await lastCommitDate(path),
		});
	}
	const pages = renderGuides(inputs, { base: BASE, repository: REPOSITORY });

	// Every directory the guides render into is theirs alone, so a page whose
	// section was renamed or removed does not linger from an earlier run.
	for (const dir of new Set(pages.map((page) => dirname(page.path)))) {
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

	await rm(STORYBOOK_TARGET, { recursive: true, force: true });
	if (existsSync(join(STORYBOOK_SOURCE, "index.html"))) {
		await cp(STORYBOOK_SOURCE, STORYBOOK_TARGET, { recursive: true });
		console.log("generate: storybook copied to public/storybook");
	} else {
		console.log("generate: no storybook-static build; /storybook/ is omitted");
	}
}

await main();
