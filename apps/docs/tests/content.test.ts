/**
 * The content readers behind the llms exports: frontmatter, sidebar order and
 * the grouping `llms.txt` lists sections by. The site is rendered by Next, so
 * these readers are the only place the export can learn what a page is called.
 */
import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
	collectPages,
	parsePage,
	sectionLabels,
	sectionPages,
} from "../scripts/lib/content";

describe("parsePage", () => {
	test("reads the title and description and keeps the body", () => {
		const page = parsePage(
			'---\ntitle: "Install"\ndescription: "Two minutes."\n---\n\nBody text.\n',
			"fallback",
		);
		expect(page.title).toBe("Install");
		expect(page.description).toBe("Two minutes.");
		expect(page.body).toBe("\nBody text.\n");
	});

	test("falls back to the name the caller knows, and drops an empty description", () => {
		const page = parsePage("No frontmatter here.\n", "Concepts");
		expect(page.title).toBe("Concepts");
		expect(page.description).toBeUndefined();
		expect(page.body).toBe("No frontmatter here.\n");
	});

	test("unquotes single-quoted values", () => {
		expect(parsePage("---\ntitle: 'Moved'\n---\n", "x").title).toBe("Moved");
	});
});

describe("collectPages", () => {
	test("walks the collection in meta.json order and names index pages by their folder", async () => {
		const root = await mkdtemp(join(tmpdir(), "qgis-sdk-docs-content-"));
		await mkdir(join(root, "start"), { recursive: true });
		await writeFile(join(root, "meta.json"), '{"pages":["start"]}');
		await writeFile(
			join(root, "start", "meta.json"),
			'{"pages":["installation","index"]}',
		);
		await writeFile(
			join(root, "start", "installation.md"),
			'---\ntitle: "Install"\n---\nBody.\n',
		);
		await writeFile(
			join(root, "start", "index.md"),
			'---\ntitle: "Start here"\n---\nIntro.\n',
		);

		const pages = await collectPages(root);
		expect(pages.map((page) => page.url)).toEqual([
			"/start/installation",
			"/start",
		]);
		expect(pages[0]?.section).toBe("start");
		expect(pages[1]?.title).toBe("Start here");
	});

	test("labels a top-level folder with its own meta.json", async () => {
		const root = await mkdtemp(join(tmpdir(), "qgis-sdk-docs-labels-"));
		await mkdir(join(root, "python"), { recursive: true });
		await writeFile(join(root, "meta.json"), '{"pages":["python"]}');
		await writeFile(join(root, "python", "meta.json"), '{"title":"Python"}');
		await writeFile(join(root, "python", "index.md"), "---\ntitle: A\n---\n");

		const labels = await sectionLabels(root);
		expect(labels).toEqual({ python: "Python" });
		const sections = sectionPages(await collectPages(root), labels);
		expect(sections).toEqual([
			{ label: "Python", pages: [expect.objectContaining({ url: "/python" })] },
		]);
	});
});

describe("sectionPages", () => {
	test("puts the collection's own pages before the folders", () => {
		const sections = sectionPages(
			[
				{ url: "/", title: "Home", body: "", section: "." },
				{ url: "/a", title: "A", body: "", section: "a" },
			],
			{ a: "Section A" },
		);
		expect(sections.map((section) => section.label)).toEqual([
			"Overview",
			"Section A",
		]);
	});
});
