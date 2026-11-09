/**
 * The AI-facing surface: `llms.txt`, `llms-full.txt`, the per-page markdown
 * exports and the gate that refuses a page without one. An agent reads these
 * instead of the HTML, so a page that renders but has no `.md` is a hole in
 * the documentation, not a cosmetic miss.
 */
import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ContentPage, ContentSection } from "../scripts/lib/content";
import {
	type LlmsOptions,
	publishedRoutes,
	renderFull,
	renderIndex,
	renderPage,
	verifyLlms,
	writeLlmsExports,
} from "../scripts/lib/llms";
import { writeSitemap } from "../scripts/lib/sitemap";

const OPTIONS: LlmsOptions = {
	site: "https://example.test",
	base: "/docs",
	title: "QGIS SDK",
	description: "A Python-first foundation.",
	repository: "https://github.com/o/r",
};

const INSTALL: ContentPage = {
	url: "/start/installation",
	title: "Install the QGIS SDK",
	description: "Two minutes.",
	body: "Install it.\n",
	section: "start",
};
const PYTHON: ContentPage = {
	url: "/python",
	title: "Python package",
	body: "The guide.\n",
	section: "python",
};

const SECTIONS: readonly ContentSection[] = [
	{ label: "Start here", pages: [INSTALL] },
	{ label: "Python package", pages: [PYTHON] },
];

describe("the llms index", () => {
	test("lists every page by its markdown URL, under its section label", () => {
		const index = renderIndex(SECTIONS, OPTIONS);
		expect(index).toContain("# QGIS SDK");
		expect(index).toContain("## Start here");
		expect(index).toContain(
			"- [Install the QGIS SDK](https://example.test/docs/start/installation.md): Two minutes.",
		);
		// No description: no dangling colon.
		expect(index).toContain(
			"- [Python package](https://example.test/docs/python.md)",
		);
		expect(index).toContain("## Optional");
	});

	test("renders one page as standalone markdown with its title", () => {
		expect(renderPage(INSTALL)).toBe(
			"# Install the QGIS SDK\n\nInstall it.\n\n",
		);
	});

	test("carries every body and its source URL in llms-full.txt", () => {
		const full = renderFull(SECTIONS, OPTIONS);
		expect(full).toContain("Source: https://example.test/docs/python/");
		expect(full).toContain("The guide.");
		expect(full).toContain("Install it.");
	});
});

describe("the write and the gate", () => {
	test("writes a .md beside each page and both index files", async () => {
		const out = await mkdtemp(join(tmpdir(), "qgis-sdk-docs-llms-"));
		const written = await writeLlmsExports(out, SECTIONS, OPTIONS);
		expect(written).toBe(2);
		expect(
			await readFile(join(out, "start/installation.md"), "utf8"),
		).toContain("# Install the QGIS SDK");
		expect(await readFile(join(out, "llms.txt"), "utf8")).toContain(
			"/start/installation.md",
		);
		expect(await readFile(join(out, "llms-full.txt"), "utf8")).toContain(
			"Install it.",
		);
	});

	test("passes when every rendered page has its markdown", async () => {
		const out = await mkdtemp(join(tmpdir(), "qgis-sdk-docs-gate-"));
		await writeLlmsExports(out, SECTIONS, OPTIONS);
		await mkdir(join(out, "start/installation"), { recursive: true });
		await writeFile(
			join(out, "start/installation/index.html"),
			"<html></html>",
		);
		await mkdir(join(out, "python"), { recursive: true });
		await writeFile(join(out, "python/index.html"), "<html></html>");
		const report = await verifyLlms(
			out,
			[INSTALL, PYTHON],
			["/", "/start/installation", "/python"],
			OPTIONS,
		);
		expect(report.broken).toEqual([]);
		expect(report.routes).toBe(3);
	});

	test("names a page that renders without a markdown export", async () => {
		const out = await mkdtemp(join(tmpdir(), "qgis-sdk-docs-hole-"));
		await writeLlmsExports(out, SECTIONS, OPTIONS);
		await mkdir(join(out, "start/installation"), { recursive: true });
		await writeFile(
			join(out, "start/installation/index.html"),
			"<html></html>",
		);
		await mkdir(join(out, "gone"), { recursive: true });
		await writeFile(join(out, "gone/index.html"), "<html></html>");
		const report = await verifyLlms(
			out,
			[INSTALL, PYTHON],
			["/start/installation", "/gone"],
			OPTIONS,
		);
		expect(report.broken).toContain("no markdown export for /gone");
		expect(report.broken).toContain("/gone is missing from llms.txt");
		expect(report.broken).toContain("/python has content but no page");
	});
});

describe("publishedRoutes", () => {
	test("lists every rendered page and skips what the export must not index", async () => {
		const out = await mkdtemp(join(tmpdir(), "qgis-sdk-docs-routes-"));
		for (const dir of [
			"_next/static",
			"storybook",
			"404",
			"_not-found",
			"python/installation",
			"contributing/workspace",
		]) {
			await mkdir(join(out, dir), { recursive: true });
			await writeFile(join(out, dir, "index.html"), "<html></html>");
		}
		await writeFile(join(out, "index.html"), "<html></html>");
		// A route handler's output and the site's own files are not pages.
		await mkdir(join(out, "api"), { recursive: true });
		await writeFile(join(out, "api", "search"), "{}");

		expect(await publishedRoutes(out)).toEqual([
			"/",
			"/contributing/workspace",
			"/python/installation",
		]);
	});
});

describe("the sitemap", () => {
	test("writes an index and a urlset for the routes it is given", async () => {
		const out = await mkdtemp(join(tmpdir(), "qgis-sdk-docs-sitemap-"));
		const count = await writeSitemap(out, ["/", "/python"], {
			site: "https://example.test",
			base: "/docs",
		});
		expect(count).toBe(2);
		const urls = await readFile(join(out, "sitemap-0.xml"), "utf8");
		expect(urls).toContain("<loc>https://example.test/docs/</loc>");
		expect(urls).toContain("<loc>https://example.test/docs/python/</loc>");
		expect(await readFile(join(out, "sitemap-index.xml"), "utf8")).toContain(
			"https://example.test/docs/sitemap-0.xml",
		);
	});
});
