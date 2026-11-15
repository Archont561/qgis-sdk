/**
 * One component registry, and the routes that must not have another.
 *
 * Fumadocs renders MDX with whatever `components` map the route passes, so a
 * route is free to pass two, or one that drifted. The failure is quiet in the
 * direction that matters: a component missing from the map throws only when a
 * page uses it, so a page can sit unbuildable until someone writes it, and a
 * second map on another route rebuilds the same list by hand.
 *
 * The registry is `lib/mdx.tsx`; these tests hold its contents and assert both
 * routes take their components from it.
 */
import { describe, expect, test } from "bun:test";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { COMPONENT_NAMES, mdxComponents } from "../lib/mdx";

const DOCS = join(import.meta.dir, "..");

async function source(path: string): Promise<string> {
	return readFile(join(DOCS, path), "utf8");
}

/** Every `.tsx` file under `app/`, as repository-relative paths. */
async function routes(directory = "app"): Promise<string[]> {
	const entries = await readdir(join(DOCS, directory), { withFileTypes: true });
	const out: string[] = [];
	for (const entry of entries) {
		const path = `${directory}/${entry.name}`;
		if (entry.isDirectory()) {
			out.push(...(await routes(path)));
			continue;
		}
		if (entry.name.endsWith(".tsx")) out.push(path);
	}
	return out;
}

describe("the registry", () => {
	test("carries every component the guides and the phases name", () => {
		for (const name of COMPONENT_NAMES) {
			expect(mdxComponents).toHaveProperty(name);
		}
	});

	test("keeps the Fumadocs defaults, so prose keeps its code blocks", () => {
		for (const name of ["pre", "a", "img", "table", "h2", "CodeBlockTabs"]) {
			expect(mdxComponents).toHaveProperty(name);
		}
	});
});

describe("the routes", () => {
	test("the docs route passes the registry and nothing else", async () => {
		const page = await source("app/[...slug]/page.tsx");
		expect(page).toContain('import { mdxComponents } from "@/lib/mdx";');
		expect(page).toContain("<MDX components={mdxComponents} />");
		// A second map would be a second registry; an inline object literal or a
		// spread of the defaults are both that.
		expect(page).not.toContain("components={{");
		expect(page).not.toContain("defaultMdxComponents");
	});

	test("the landing page takes its components from the registry too", async () => {
		const home = await source("app/page.tsx");
		expect(home).toContain('from "@/lib/mdx"');
	});

	test("no route imports a Fumadocs component directly", async () => {
		for (const path of await routes()) {
			expect(await source(path)).not.toContain("fumadocs-ui/components/");
		}
	});
});
