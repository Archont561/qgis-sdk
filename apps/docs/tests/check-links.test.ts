/**
 * The link check over a built site: every internal `href` resolves to a file
 * in `dist/`, and every fragment to an element id on that page.
 */
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { checkLinks } from "../scripts/lib/links";

let dist = "";

async function page(path: string, html: string): Promise<void> {
	const target = join(dist, path);
	await mkdir(join(target, ".."), { recursive: true });
	await writeFile(target, html);
}

beforeAll(async () => {
	dist = await mkdtemp(join(tmpdir(), "qgis-sdk-docs-"));
	await page(
		"index.html",
		`<html><body>
			<a href="/qgis-sdk/python/">guide</a>
			<a href="/qgis-sdk/python/installation/#from-pypi">anchor</a>
			<a href="/qgis-sdk/python/installation/">page</a>
			<a href="/qgis-sdk/llms.txt">file</a>
			<a href="/qgis-sdk/favicon.svg">asset</a>
			<a href="https://example.com/">external</a>
			<a href="mailto:x@example.com">mail</a>
			<a href="#top">self</a>
			<a id="top"></a>
			<img src="/qgis-sdk/_astro/logo.svg">
		</body></html>`,
	);
	await page(
		"python/index.html",
		`<html><body><a href="/qgis-sdk/missing/">gone</a><a href="../start/#nope">frag</a></body></html>`,
	);
	await page(
		"python/installation/index.html",
		`<html><body><h2 id="from-pypi">From PyPI</h2><a href="/qgis-sdk/python/#x">bad-frag</a></body></html>`,
	);
	await page("start/index.html", "<html><body><p id='yes'></p></body></html>");
	await writeFile(join(dist, "llms.txt"), "# x");
	await writeFile(join(dist, "favicon.svg"), "<svg/>");
	await mkdir(join(dist, "_astro"), { recursive: true });
	await writeFile(join(dist, "_astro", "logo.svg"), "<svg/>");
});

afterAll(async () => {
	await rm(dist, { recursive: true, force: true });
});

describe("checkLinks", () => {
	test("accepts pages, files, assets, fragments, externals and reports the rest", async () => {
		const report = await checkLinks(dist, { base: "/qgis-sdk" });
		expect(report.pages).toBe(4);
		expect(report.checked).toBeGreaterThanOrEqual(10);
		expect(
			report.broken.map((b) => `${b.page} ${b.href} ${b.reason}`).sort(),
		).toEqual([
			"python/index.html ../start/#nope missing fragment #nope in start/index.html",
			"python/index.html /qgis-sdk/missing/ no such file missing/index.html",
			"python/installation/index.html /qgis-sdk/python/#x missing fragment #x in python/index.html",
		]);
	});

	test("rejects an internal link that forgets the base", async () => {
		await page("start/nobase/index.html", `<a href="/python/">no base</a>`);
		const report = await checkLinks(dist, { base: "/qgis-sdk" });
		expect(report.broken.map((b) => b.reason)).toContain(
			"outside base /qgis-sdk/",
		);
		await rm(join(dist, "start/nobase"), { recursive: true });
	});
});
