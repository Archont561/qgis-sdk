/**
 * The guide renderer: backlog guides in, Starlight pages out.
 *
 * A guide is one long markdown file (doc-12 is 2,500 lines). The site shows
 * it as one page per `##` section under a per-guide directory, with the
 * guide's preamble as the directory's index. Links the guides write for the
 * backlog (`#anchor`, `doc-13 ... .md#anchor`, `../../decisions/...`) have to
 * keep working once the sections live on separate routes.
 */
import { describe, expect, test } from "bun:test";
import {
	GUIDES,
	type Guide,
	renderGuides,
	slugify,
	splitGuide,
} from "../scripts/lib/guides";

const PYTHON: Guide = {
	id: "doc-12",
	file: "doc-12 - qgis-sdk-Python-package-guide.md",
	section: "python",
	label: "Python package",
};
const TYPESCRIPT: Guide = {
	id: "doc-13",
	file: "doc-13 - qgis-sdk-TypeScript-package-guide.md",
	section: "typescript",
	label: "TypeScript SDK",
};

const PYTHON_GUIDE = `---
id: doc-12
title: qgis-sdk Python package guide
type: guide
---
# qgis-sdk Python package guide

The reference prose for the \`qgis-sdk\` Python package; see
[decision-29](../../decisions/decision-29%20-%20Keep-READMEs-minimal.md) and
[doc-13](doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#transport-client).

## Installation

\`\`\`sh
pip install qgis-sdk
# or in a Pixi workspace:
pixi add qgis-sdk
\`\`\`

See [Scoped jobs](#scoped-jobs) and [the picker](#layer-picker).

## Desktop host: \`host()\` and the project manifest

Intro paragraph with a [task](../../tasks/task-1%20-%20Scaffold.md) and a
[plan](../plans/doc-17%20-%20Train.md).

### Layer picker

Nested text.

#### Deeper

## Scoped jobs

Jobs text linking [external](https://example.com/x) and
[0.4.0 notes](doc-13%20-%20qgis-sdk-TypeScript-package-guide.md#040-migration-notes).
`;

const TYPESCRIPT_GUIDE = `---
id: doc-13
title: qgis-sdk TypeScript package guide
type: guide
---
# qgis-sdk TypeScript package guide

The page side. Companion: [doc-12](doc-12%20-%20qgis-sdk-Python-package-guide.md).

## Transport client

Text.

## 0.4.0 migration notes

Text.
`;

describe("slugify", () => {
	test("matches the GitHub anchors the guides already link to", () => {
		expect(slugify("Scoped jobs")).toBe("scoped-jobs");
		expect(slugify("Desktop host: `host()` and the project manifest")).toBe(
			"desktop-host-host-and-the-project-manifest",
		);
		expect(slugify("Stores: the framework-free core")).toBe(
			"stores-the-framework-free-core",
		);
		expect(slugify("Components: `@archont561/qgis-sdk-ui`")).toBe(
			"components-archont561qgis-sdk-ui",
		);
		expect(slugify("0.4.0 migration notes")).toBe("040-migration-notes");
		expect(slugify("0.5.0 release gate (TASK-31, 2026-10-25)")).toBe(
			"050-release-gate-task-31-2026-10-25",
		);
	});
});

describe("splitGuide", () => {
	const guide = splitGuide(PYTHON_GUIDE);

	test("takes the title from the H1 and the preamble up to the first section", () => {
		expect(guide.title).toBe("qgis-sdk Python package guide");
		expect(guide.intro).toContain("The reference prose");
		expect(guide.intro).not.toContain("## Installation");
		expect(guide.intro).not.toContain("id: doc-12");
	});

	test("yields one section per H2 with its own slug and body", () => {
		expect(guide.sections.map((s) => s.slug)).toEqual([
			"installation",
			"desktop-host-host-and-the-project-manifest",
			"scoped-jobs",
		]);
		expect(guide.sections[1]?.heading).toBe(
			"Desktop host: `host()` and the project manifest",
		);
		expect(guide.sections[2]?.body).toContain("Jobs text");
	});

	test("ignores `#` lines inside fenced code", () => {
		expect(guide.sections[0]?.body).toContain("# or in a Pixi workspace:");
		expect(guide.sections.map((s) => s.heading)).not.toContain(
			"or in a Pixi workspace:",
		);
	});

	test("indexes every heading of every level to the page that holds it", () => {
		expect(guide.anchors.get("layer-picker")).toEqual({
			page: "desktop-host-host-and-the-project-manifest",
			anchor: "layer-picker",
		});
		expect(guide.anchors.get("deeper")?.page).toBe(
			"desktop-host-host-and-the-project-manifest",
		);
		expect(guide.anchors.get("scoped-jobs")).toEqual({
			page: "scoped-jobs",
			anchor: null,
		});
	});
});

describe("renderGuides", () => {
	const pages = renderGuides(
		[
			{ guide: PYTHON, markdown: PYTHON_GUIDE, lastUpdated: "2026-10-27" },
			{ guide: TYPESCRIPT, markdown: TYPESCRIPT_GUIDE },
		],
		{ base: "/qgis-sdk", repository: "https://github.com/Archont561/qgis-sdk" },
	);
	const byPath = new Map(pages.map((p) => [p.path, p.content]));

	test("writes an index per guide and one page per section", () => {
		expect([...byPath.keys()].sort()).toEqual([
			"python/desktop-host-host-and-the-project-manifest.md",
			"python/index.md",
			"python/installation.md",
			"python/scoped-jobs.md",
			"typescript-migration/v0-4.md",
			"typescript/index.md",
			"typescript/transport-client.md",
		]);
	});

	test("carries Starlight frontmatter: a plain-text title, a description and the order", () => {
		const page =
			byPath.get("python/desktop-host-host-and-the-project-manifest.md") ?? "";
		expect(page.startsWith("---\n")).toBe(true);
		expect(page).toContain(
			'title: "Desktop host: host() and the project manifest"',
		);
		expect(page).toContain("description: ");
		expect(page).toContain("sidebar:\n  order: 2\n");
		const index = byPath.get("python/index.md") ?? "";
		expect(index).toContain('title: "qgis-sdk Python package guide"');
		expect(index).toContain('sidebar:\n  label: "Overview"\n  order: 0\n');
		expect(index).toContain("\nlastUpdated: 2026-10-27\n"); // a YAML date, unquoted
		expect(byPath.get("typescript/index.md")).not.toContain("lastUpdated");
	});

	test("every page edits the guide it came from, not the generated file", () => {
		for (const [path, content] of byPath) {
			expect(content, path).toContain(
				'editUrl: "https://github.com/Archont561/qgis-sdk/edit/main/backlog/docs/guides/doc-1',
			);
		}
	});

	test("reports a link whose anchor no guide has instead of inventing a route", () => {
		const broken = renderGuides(
			[{ guide: PYTHON, markdown: "# T\n\n## A\n\nSee [x](#nowhere).\n" }],
			{ base: "", repository: "https://github.com/o/r" },
		);
		expect(broken.warnings).toEqual([
			{
				guide: "doc-12",
				page: "a",
				link: "#nowhere",
				reason: "no heading #nowhere in doc-12",
			},
		]);
		expect(broken.find((p) => p.path === "python/a.md")?.content).toContain(
			"[x](#nowhere)",
		);
	});

	test("demotes the section's subheadings so the page title is the only H1", () => {
		const page =
			byPath.get("python/desktop-host-host-and-the-project-manifest.md") ?? "";
		expect(page).toContain("\n## Layer picker\n");
		expect(page).toContain("\n### Deeper\n");
		expect(page).not.toContain("\n#### ");
		expect(page).not.toMatch(/\n# /);
	});

	test("rewrites same-guide anchors to the page that now holds the heading", () => {
		const page = byPath.get("python/installation.md") ?? "";
		expect(page).toContain("[Scoped jobs](/qgis-sdk/python/scoped-jobs/)");
		expect(page).toContain(
			"[the picker](/qgis-sdk/python/desktop-host-host-and-the-project-manifest/#layer-picker)",
		);
	});

	test("rewrites cross-guide links, with or without an anchor", () => {
		expect(byPath.get("python/index.md")).toContain(
			"[doc-13](/qgis-sdk/typescript/transport-client/)",
		);
		expect(byPath.get("python/scoped-jobs.md")).toContain(
			"[0.4.0 notes](/qgis-sdk/typescript/migration/v0-4/)",
		);
		expect(byPath.get("typescript/index.md")).toContain(
			"[doc-12](/qgis-sdk/python/)",
		);
	});

	test("drops links to process records and keeps their text", () => {
		// Tasks, plans, milestones and the agent rules are how the repository
		// works, not what it ships: the site never links them (the prose that
		// cites them is edited at the source; this is the safety net).
		const page =
			byPath.get("python/desktop-host-host-and-the-project-manifest.md") ?? "";
		expect(page).toContain("Intro paragraph with a task and a\nplan.");
		expect(page).not.toContain("backlog/tasks");
		expect(page).not.toContain("backlog/docs/plans");
		expect(pages.warnings).toContainEqual({
			guide: "doc-12",
			page: "desktop-host-host-and-the-project-manifest",
			link: "../../tasks/task-1%20-%20Scaffold.md",
			reason: "cites a process record; the link was dropped",
		});
		const rules = renderGuides(
			[
				{
					guide: PYTHON,
					markdown:
						"# T\n\n## A\n\nSee [AGENTS.md](../../../AGENTS.md), [skills](../../../.agents/skills/tdd/SKILL.md) and [m-6](../../milestones/m-6%20-%200.7.0.md).\n",
				},
			],
			{ base: "", repository: "https://github.com/o/r" },
		);
		expect(rules.find((p) => p.path === "python/a.md")?.content).toContain(
			"See AGENTS.md, skills and m-6.",
		);
		expect(rules.warnings).toHaveLength(3);
	});

	test("points a decision at its row on the design-decisions page", () => {
		expect(byPath.get("python/index.md")).toContain(
			"[decision-29](/qgis-sdk/reference/design-decisions/#decision-29)",
		);
		expect(byPath.get("python/index.md")).not.toContain("backlog/decisions");
	});

	test("points other backlog records the site does not render at the repository", () => {
		const other = renderGuides(
			[
				{
					guide: PYTHON,
					markdown:
						"# T\n\n## A\n\nSee [doc-26](../specifications/doc-26%20-%20Authority.md#assets).\n",
				},
			],
			{ base: "", repository: "https://github.com/o/r" },
		);
		expect(other.find((p) => p.path === "python/a.md")?.content).toContain(
			"[doc-26](https://github.com/o/r/blob/main/backlog/docs/specifications/doc-26%20-%20Authority.md#assets)",
		);
	});

	test("leaves absolute links and code alone", () => {
		const page = byPath.get("python/scoped-jobs.md") ?? "";
		expect(page).toContain("[external](https://example.com/x)");
		expect(byPath.get("python/installation.md")).toContain(
			"pip install qgis-sdk\n# or in a Pixi",
		);
	});

	test("gates notes on an unreleased line behind a Draft badge and aside", () => {
		const drafts = renderGuides(
			[
				{
					guide: PYTHON,
					markdown:
						"# T\n\n## 0.7.0 migration notes (in progress)\n\nBody.\n\n## 0.6.0 migration notes\n\nDone.\n",
				},
				{
					guide: TYPESCRIPT,
					markdown:
						"# T\n\n## Next minor (unreleased) migration notes\n\nBody.\n",
				},
			],
			{ base: "", repository: "https://github.com/o/r" },
		);
		const draft =
			drafts.find((p) => p.path === "python-migration/v0-7.md")?.content ?? "";
		expect(draft).toContain(
			'sidebar:\n  order: 993\n  badge: {"text":"Draft","variant":"caution"}\n',
		);
		expect(draft).toContain(
			"---\n:::caution[Draft]\nThese notes describe the unreleased 0.7.0 line. Content changes as the release is cut.\n:::\n\nBody.\n",
		);
		const next =
			drafts.find((p) => p.path === "typescript-migration/next-minor.md")
				?.content ?? "";
		expect(next).toContain('badge: {"text":"Draft","variant":"caution"}');
		expect(next).toContain(
			"These notes describe the unreleased next minor. Content changes as the release is cut.",
		);
		const released =
			drafts.find((p) => p.path === "python-migration/v0-6.md")?.content ?? "";
		expect(released).not.toContain("badge");
		expect(released).not.toContain(":::caution");
	});

	test("the index lists the guide's sections", () => {
		const index = byPath.get("python/index.md") ?? "";
		expect(index).toContain("- [Installation](/qgis-sdk/python/installation/)");
		expect(index).toContain(
			"- [Desktop host: `host()` and the project manifest](/qgis-sdk/python/desktop-host-host-and-the-project-manifest/)",
		);
	});
});

describe("migration notes", () => {
	const pages = renderGuides(
		[
			{
				guide: PYTHON,
				markdown: [
					"# T",
					"",
					"## Installation",
					"",
					"See [the 0.4 notes](#040-migration-notes) and [the policy](#010-experimental-release-and-migration-policy).",
					"",
					"## 0.1.0 experimental release and migration policy",
					"",
					"Policy.",
					"",
					"## 0.7.0 migration notes (in progress)",
					"",
					"Soon.",
					"",
					"### Parameter kinds",
					"",
					"Kinds.",
					"",
					"## 0.4.0 migration notes",
					"",
					"Done. See [kinds](#parameter-kinds).",
					"",
				].join("\n"),
			},
			{
				guide: TYPESCRIPT,
				markdown:
					"# T\n\n## Exports\n\nSee [doc-12 0.4](doc-12%20-%20qgis-sdk-Python-package-guide.md#040-migration-notes).\n\n## 0.3.0 migration notes\n\nBody.\n",
			},
		],
		{ base: "/qgis-sdk", repository: "https://github.com/o/r" },
	);
	const byPath = new Map(pages.map((p) => [p.path, p.content]));

	test("live in a sibling directory with a slug under the guide's route", () => {
		expect([...byPath.keys()].sort()).toEqual([
			"python-migration/v0-1-experimental-policy.md",
			"python-migration/v0-4.md",
			"python-migration/v0-7.md",
			"python/index.md",
			"python/installation.md",
			"typescript-migration/v0-3.md",
			"typescript/exports.md",
			"typescript/index.md",
		]);
		expect(byPath.get("python-migration/v0-4.md")).toContain(
			'slug: "python/migration/v0-4"',
		);
		expect(byPath.get("typescript-migration/v0-3.md")).toContain(
			'slug: "typescript/migration/v0-3"',
		);
	});

	test("carry a human title and sort newest first", () => {
		expect(byPath.get("python-migration/v0-7.md")).toContain(
			'title: "0.7.0 migration notes"',
		);
		expect(
			byPath.get("python-migration/v0-1-experimental-policy.md"),
		).toContain('title: "0.1.0 experimental release and migration policy"');
		const order = (path: string): number =>
			Number(/order: (\d+)/.exec(byPath.get(path) ?? "")?.[1]);
		expect(order("python-migration/v0-7.md")).toBeLessThan(
			order("python-migration/v0-4.md"),
		);
		expect(order("python-migration/v0-4.md")).toBeLessThan(
			order("python-migration/v0-1-experimental-policy.md"),
		);
	});

	test("are reached by the anchors the guides already use", () => {
		const installation = byPath.get("python/installation.md") ?? "";
		expect(installation).toContain(
			"[the 0.4 notes](/qgis-sdk/python/migration/v0-4/)",
		);
		expect(installation).toContain(
			"[the policy](/qgis-sdk/python/migration/v0-1-experimental-policy/)",
		);
		expect(byPath.get("python-migration/v0-4.md")).toContain(
			"[kinds](/qgis-sdk/python/migration/v0-7/#parameter-kinds)",
		);
		expect(byPath.get("typescript/exports.md")).toContain(
			"[doc-12 0.4](/qgis-sdk/python/migration/v0-4/)",
		);
		expect(byPath.get("python/index.md")).toContain(
			"- [0.4.0 migration notes](/qgis-sdk/python/migration/v0-4/)",
		);
		expect(pages.warnings).toHaveLength(0);
	});
});

describe("GUIDES", () => {
	test("names the three backlog guides decision-29 made the reference source", () => {
		expect(GUIDES.map((g) => [g.id, g.section])).toEqual([
			["doc-12", "python"],
			["doc-13", "typescript"],
			["doc-14", "contributing/workspace"],
		]);
	});

	test("keeps the workspace guide out of the consumer reference", () => {
		const workspace = GUIDES[2] as Guide;
		expect(workspace.label).toBe("Contributing");
		expect(workspace.title).toBe("Workspace, harnesses, and evidence");
	});
});

describe("a guide with a title of its own", () => {
	const pages = renderGuides(
		[
			{
				guide: {
					id: "doc-14",
					file: "doc-14 - W.md",
					section: "contributing/workspace",
					label: "Contributing",
					title: "Workspace, harnesses, and evidence",
				},
				markdown:
					"# Workspace development\n\nIntro.\n\n## Quick start\n\nRun it.\n",
			},
			{
				guide: PYTHON,
				markdown:
					"# P\n\n## A\n\nSee [the harness](doc-14%20-%20W.md#quick-start).\n",
			},
		],
		{ base: "/qgis-sdk", repository: "https://github.com/o/r" },
	);

	test("titles the index with the override and nests the pages", () => {
		const index = pages.find(
			(p) => p.path === "contributing/workspace/index.md",
		);
		expect(index?.content).toContain(
			'title: "Workspace, harnesses, and evidence"',
		);
		expect(index?.content).toContain(
			"- [Quick start](/qgis-sdk/contributing/workspace/quick-start/)",
		);
		expect(
			pages.find((p) => p.path === "contributing/workspace/quick-start.md")
				?.content,
		).toContain('description: "Run it."');
	});

	test("routes cross-guide links at the nested directory", () => {
		expect(pages.find((p) => p.path === "python/a.md")?.content).toContain(
			"[the harness](/qgis-sdk/contributing/workspace/quick-start/)",
		);
	});
});
