/**
 * Write the generated half of `src/content/docs/` before `astro dev|build`.
 *
 * - the three backlog guides, one directory each (see `lib/guides.ts`);
 * - `public/storybook/`, a copy of `packages/qgis-sdk-ui/storybook-static`
 *   when it has been built, so the component Storybook ships with the site.
 *
 * Both outputs are ignored by git; the sources are the guides and the stories.
 * `lastUpdated` comes from the guide's last commit, so a page is as fresh as
 * the prose it renders rather than as the build that rendered it.
 */

import { existsSync } from "node:fs";
import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { BASE, REPOSITORY } from "../site";
import { GUIDES, type GuideInput, renderGuides } from "./lib/guides";

const DOCS_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(DOCS_DIR, "../../..");
const GUIDES_DIR = join(ROOT, "backlog/docs/guides");
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

	for (const guide of GUIDES) {
		await rm(join(CONTENT_DIR, guide.section), {
			recursive: true,
			force: true,
		});
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

	await rm(STORYBOOK_TARGET, { recursive: true, force: true });
	if (existsSync(join(STORYBOOK_SOURCE, "index.html"))) {
		await cp(STORYBOOK_SOURCE, STORYBOOK_TARGET, { recursive: true });
		console.log("generate: storybook copied to public/storybook");
	} else {
		console.log("generate: no storybook-static build; /storybook/ is omitted");
	}
}

await main();
