/** Compatibility pages are static output, not Starlight content. */
import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { runInNewContext } from "node:vm";
import {
	LEGACY_ROUTES,
	verifyRedirectSurfaces,
	writeRedirects,
} from "../scripts/lib/redirects";

let dist = "";
afterEach(async () => {
	if (dist) await rm(dist, { recursive: true, force: true });
	dist = "";
});

describe("legacy routes", () => {
	test("writes a visible fallback and retains query and fragment on navigation", async () => {
		dist = await mkdtemp(join(tmpdir(), "qgis-sdk-redirect-"));
		const target = join(
			dist,
			"contributing/workspace/desktop-lifecycle-harnesses/index.html",
		);
		await mkdir(dirname(target), { recursive: true });
		await writeFile(
			target,
			'<h2 id="real-desktop-startup-and-unload-evidence">Evidence</h2>',
		);
		await writeRedirects(dist, {
			"workspace/desktop-lifecycle-harnesses":
				"contributing/workspace/desktop-lifecycle-harnesses",
		});
		const html = await readFile(
			join(dist, "workspace/desktop-lifecycle-harnesses/index.html"),
			"utf8",
		);
		expect(html).toContain(
			'href="/qgis-sdk/contributing/workspace/desktop-lifecycle-harnesses/"',
		);
		expect(html).toContain('content="noindex, follow"');
		expect(html).toContain(
			'rel="canonical" href="https://archont561.github.io/qgis-sdk/contributing/workspace/desktop-lifecycle-harnesses/"',
		);
		expect(html).toContain('<noscript><meta http-equiv="refresh"');
		const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
		expect(script).toBeDefined();
		let result = "";
		runInNewContext(script ?? "", {
			location: {
				search: "?from=old",
				hash: "#real-desktop-startup-and-unload-evidence",
				replace: (url: string) => {
					result = url;
				},
			},
		});
		expect(result).toBe(
			"/qgis-sdk/contributing/workspace/desktop-lifecycle-harnesses/?from=old#real-desktop-startup-and-unload-evidence",
		);
	});
	test("refuses to replace an existing page or link to a missing target", async () => {
		dist = await mkdtemp(join(tmpdir(), "qgis-sdk-redirect-"));
		await mkdir(join(dist, "old"));
		await writeFile(join(dist, "old/index.html"), "existing page");
		await mkdir(join(dist, "target"));
		await writeFile(join(dist, "target/index.html"), "target");
		await expect(writeRedirects(dist, { old: "target" })).rejects.toThrow();
		expect(await readFile(join(dist, "old/index.html"), "utf8")).toBe(
			"existing page",
		);
		await expect(writeRedirects(dist, { other: "missing" })).rejects.toThrow();
	});

	test("maps previously published migration and workspace URLs to their current pages", () => {
		expect(
			LEGACY_ROUTES["python/010-experimental-release-and-migration-policy"],
		).toBe("python/migration/v0-1-experimental-policy");
		for (const version of [2, 3, 4, 5, 6, 7]) {
			expect(LEGACY_ROUTES[`python/0${version}0-migration-notes`]).toBe(
				`python/migration/v0-${version}`,
			);
		}
		expect(LEGACY_ROUTES["python/070-migration-notes-in-progress"]).toBe(
			"python/migration/v0-7",
		);
		for (const version of [2, 3, 4, 5]) {
			expect(LEGACY_ROUTES[`typescript/0${version}0-migration-notes`]).toBe(
				`typescript/migration/v0-${version}`,
			);
		}
		expect(
			LEGACY_ROUTES["typescript/next-minor-unreleased-migration-notes"],
		).toBe("typescript/migration/v0-5");
		expect(LEGACY_ROUTES.workspace).toBe("contributing/workspace");
		expect(LEGACY_ROUTES["workspace/quick-start"]).toBe(
			"contributing/workspace/quick-start",
		);
		expect(LEGACY_ROUTES["workspace/040-release-gate-task-30-2026-10-25"]).toBe(
			"contributing/workspace/040-release-gate-2026-10-25",
		);
	});

	test("checks that the sitemap and machine surfaces index destinations, not legacy routes", async () => {
		dist = await mkdtemp(join(tmpdir(), "qgis-sdk-surfaces-"));
		await mkdir(join(dist, "python/migration"), { recursive: true });
		await writeFile(join(dist, "python/migration/v0-4.md"), "notes");
		await writeFile(join(dist, "robots.txt"), "sitemap");
		await writeFile(join(dist, "sitemap-index.xml"), "sitemap-0.xml");
		await writeFile(join(dist, "llms-full.txt"), "notes");
		await writeFile(
			join(dist, "llms.txt"),
			"https://archont561.github.io/qgis-sdk/python/migration/v0-4.md",
		);
		const sitemap = join(dist, "sitemap-0.xml");
		const current =
			"<loc>https://archont561.github.io/qgis-sdk/python/migration/v0-4/</loc>";
		await writeFile(sitemap, current);
		const routes = { "python/040-migration-notes": "python/migration/v0-4" };
		await expect(verifyRedirectSurfaces(dist, routes)).resolves.toBeUndefined();
		await writeFile(
			sitemap,
			`${current}<loc>https://archont561.github.io/qgis-sdk/python/040-migration-notes/</loc>`,
		);
		await expect(verifyRedirectSurfaces(dist, routes)).rejects.toThrow(
			"legacy route in sitemap",
		);
		await writeFile(sitemap, current);
		await writeFile(
			join(dist, "llms.txt"),
			"https://archont561.github.io/qgis-sdk/python/migration/v0-4.md\nhttps://archont561.github.io/qgis-sdk/python/040-migration-notes.md",
		);
		await expect(verifyRedirectSurfaces(dist, routes)).rejects.toThrow(
			"legacy route in llms.txt",
		);
	});
});
