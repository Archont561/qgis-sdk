/** Reference sources stay editable and historical backlog anchors remain navigable. */
import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { GUIDES, splitGuide } from "../scripts/lib/guides";

const root = fileURLToPath(new URL("../../..", import.meta.url));

describe("reference guide sources", () => {
	for (const guide of GUIDES) {
		test(`${guide.id} has a site-owned source and compatible historical headings`, async () => {
			const source = resolve(root, "apps/docs/guides", guide.file);
			const legacy = resolve(root, "backlog/docs/guides", guide.file);
			const markdown = await Bun.file(source).text();
			const stub = await Bun.file(legacy).text();
			const sourceAnchors = splitGuide(markdown).anchors;
			const oldAnchors = splitGuide(stub).anchors;
			for (const anchor of oldAnchors.keys()) {
				expect(sourceAnchors.has(anchor)).toBe(true);
			}
			expect(stub).toContain("apps/docs/guides");
			// Ordinary links in the editable source should still resolve on GitHub.
			const prose = markdown.replace(/```[\s\S]*?```/g, "");
			for (const match of prose.matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)) {
				const url = match[1] ?? "";
				if (/^(?:[a-z][a-z0-9+.-]*:|\/|#)/i.test(url)) continue;
				const path = decodeURIComponent(url.split("#", 1)[0] ?? "");
				expect(existsSync(resolve(dirname(source), path))).toBe(true);
			}
		});
	}
	test("historical links use GitHub's source-heading fragments", async () => {
		const python = await Bun.file(
			resolve(root, "backlog/docs/guides", GUIDES[0]?.file ?? ""),
		).text();
		const typescript = await Bun.file(
			resolve(root, "backlog/docs/guides", GUIDES[1]?.file ?? ""),
		).text();
		expect(python).toContain("#what-does-describe_plugin-do-and-not-do)");
		expect(python).toContain("#testing-surfaces-without-qgis-build_surface)");
		expect(typescript).toContain(
			"#formstore--formstoreqgis-actionid--initial-)",
		);
	});
});
