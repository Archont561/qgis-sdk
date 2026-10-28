/** Static compatibility pages written after Astro, outside the sitemap and llms output. */
import { access, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { BASE, SITE } from "../../site";

/** Published before the guide routes were reorganised. Keep historical slugs,
 * including the draft names and the earlier release-gate titles. */
const WORKSPACE_SECTIONS = [
	"quick-start",
	"development-environments",
	"reproducible-sandbox",
	"test-build-and-the-pixi-tasks",
	"repository-layout",
	"documentation-site",
	"contributing",
	"python-package-development",
	"test-layers",
	"contract-generation-checked-example",
	"build-artifacts",
	"developer-scripts",
	"headless-qgis-and-webengine-qualification",
	"desktop-lifecycle-harnesses",
	"040-release-gate-2026-10-25",
	"050-release-gate-2026-10-25",
	"060-release-gate-2026-10-26",
	"split-release-pipeline-rehearsal",
	"ui-release-train-rehearsal-2026-10-27",
] as const;

export const LEGACY_ROUTES: Readonly<Record<string, string>> = {
	workspace: "contributing/workspace",
	...Object.fromEntries(
		WORKSPACE_SECTIONS.map((section) => [
			`workspace/${section}`,
			`contributing/workspace/${section}`,
		]),
	),
	"workspace/040-release-gate-task-30-2026-10-25":
		"contributing/workspace/040-release-gate-2026-10-25",
	"workspace/050-release-gate-task-31-2026-10-25":
		"contributing/workspace/050-release-gate-2026-10-25",
	"workspace/060-release-gate-task-60-2026-10-26":
		"contributing/workspace/060-release-gate-2026-10-26",
	"workspace/split-release-pipeline-rehearsal-task-57-ac-3":
		"contributing/workspace/split-release-pipeline-rehearsal",
	"workspace/ui-release-train-rehearsal-task-110-2026-10-27":
		"contributing/workspace/ui-release-train-rehearsal-2026-10-27",
	"python/010-experimental-release-and-migration-policy":
		"python/migration/v0-1-experimental-policy",
	...Object.fromEntries(
		[2, 3, 4, 5, 6, 7].map((version) => [
			`python/0${version}0-migration-notes`,
			`python/migration/v0-${version}`,
		]),
	),
	"python/070-migration-notes-in-progress": "python/migration/v0-7",
	...Object.fromEntries(
		[2, 3, 4, 5].map((version) => [
			`typescript/0${version}0-migration-notes`,
			`typescript/migration/v0-${version}`,
		]),
	),
	"typescript/next-minor-unreleased-migration-notes":
		"typescript/migration/v0-5",
};

export async function writeRedirects(
	dist: string,
	routes: Readonly<Record<string, string>>,
): Promise<void> {
	for (const [oldPath, newPath] of Object.entries(routes)) {
		const target = `${BASE}/${newPath}/`;
		await access(join(dist, newPath, "index.html"));
		const dir = join(dist, oldPath);
		await mkdir(dir, { recursive: true });
		const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Page moved</title>
<meta name="robots" content="noindex, follow">
<link rel="canonical" href="${SITE}${target}">
<noscript><meta http-equiv="refresh" content="0; url=${target}"></noscript>
<script>location.replace(${JSON.stringify(target)} + location.search + location.hash);</script>
</head><body><p>This page has moved. <a href="${target}">Continue to the new page</a>.</p></body></html>\n`;
		await writeFile(join(dir, "index.html"), html, { flag: "wx" });
	}
}

/** Fail the build if compatibility pages become indexed or their targets disappear. */
export async function verifyRedirectSurfaces(
	dist: string,
	routes: Readonly<Record<string, string>>,
): Promise<void> {
	const sitemapFiles = (await readdir(dist)).filter((name) =>
		/^sitemap-\d+\.xml$/.test(name),
	);
	if (sitemapFiles.length === 0) throw new Error("no sitemap pages");
	const sitemap = (
		await Promise.all(
			sitemapFiles.map((name) => readFile(join(dist, name), "utf8")),
		)
	).join("\n");
	const llms = await readFile(join(dist, "llms.txt"), "utf8");
	await Promise.all(
		["robots.txt", "sitemap-index.xml", "llms-full.txt"].map((name) =>
			access(join(dist, name)),
		),
	);
	for (const [oldPath, newPath] of Object.entries(routes)) {
		if (sitemap.includes(`<loc>${SITE}${BASE}/${oldPath}/</loc>`))
			throw new Error(`legacy route in sitemap: ${oldPath}`);
		if (!sitemap.includes(`<loc>${SITE}${BASE}/${newPath}/</loc>`))
			throw new Error(`destination missing from sitemap: ${newPath}`);
		if (llms.includes(`${SITE}${BASE}/${oldPath}.md`))
			throw new Error(`legacy route in llms.txt: ${oldPath}`);
		if (!llms.includes(`${SITE}${BASE}/${newPath}.md`))
			throw new Error(`destination missing from llms.txt: ${newPath}`);
		await access(join(dist, `${newPath}.md`));
	}
}
