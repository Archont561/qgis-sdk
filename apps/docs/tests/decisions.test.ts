/**
 * The decisions page: ADR frontmatter in, one curated reference page out.
 *
 * The facts (number, title, status, date) come from the records so a status
 * promotion in the backlog reaches the site on the next build; the one-line
 * summary is editorial and lives in `scripts/decision-summaries.ts`.
 */
import { describe, expect, test } from "bun:test";
import { parseDecision, renderDecisionsPage } from "../scripts/lib/decisions";

const FILE =
	"decision-25 - Version-each-package-independently-behind-a-shared-contract-version.md";
const RECORD = `---
id: decision-25
title: Version each package independently behind a shared contract version
date: '2026-10-24 18:02'
status: accepted
---
## Context

Prose.
`;

const FOLDED = `---
id: decision-64
title: >-
  Generate the Processing catalogue from the host registry and run any
  registered algorithm through one typed surface
date: '2026-10-27'
status: proposed
---
`;

describe("parseDecision", () => {
	test("reads number, title, status and the date without its time", () => {
		expect(parseDecision(FILE, RECORD)).toEqual({
			number: 25,
			file: FILE,
			title:
				"Version each package independently behind a shared contract version",
			status: "accepted",
			date: "2026-10-24",
		});
	});

	test("joins a folded title", () => {
		const decision = parseDecision("decision-64 - x.md", FOLDED);
		expect(decision.title).toBe(
			"Generate the Processing catalogue from the host registry and run any registered algorithm through one typed surface",
		);
		expect(decision.status).toBe("proposed");
		expect(decision.date).toBe("2026-10-27");
	});

	test("refuses a record missing a field", () => {
		expect(() =>
			parseDecision("decision-3 - x.md", "---\ntitle: T\n---\n"),
		).toThrow("decision-3 - x.md: frontmatter lacks date");
	});
});

describe("renderDecisionsPage", () => {
	const decisions = [
		parseDecision("decision-64 - x.md", FOLDED),
		parseDecision(FILE, RECORD),
	];
	const page = renderDecisionsPage(
		decisions,
		{ 25: "Each package versions on its own behind a shared contract." },
		{ repository: "https://github.com/o/r" },
	);

	test("is a Starlight page with the table ordered by number", () => {
		expect(page.content.startsWith('---\ntitle: "Design decisions"\n')).toBe(
			true,
		);
		expect(page.content).toContain(
			"| Number | Title | Decision | Status | Date |\n| :-- | :-- | :-- | :-- | :-- |\n",
		);
		expect(page.content.indexOf("decision-25")).toBeLessThan(
			page.content.indexOf("decision-64"),
		);
	});

	test("links the record from the number alone and anchors the row", () => {
		expect(page.content).toContain(
			`| <a id="decision-25" href="https://github.com/o/r/blob/main/backlog/decisions/${encodeURIComponent(FILE)}">decision-25</a> | Version each package independently behind a shared contract version | Each package versions on its own behind a shared contract. | Accepted | 2026-10-24 |`,
		);
		expect(page.content).not.toContain("[Version each package");
	});

	test("falls back to the title and reports a decision without a summary", () => {
		expect(page.content).toContain(
			"| Generate the Processing catalogue from the host registry and run any registered algorithm through one typed surface | Generate the Processing catalogue from the host registry and run any registered algorithm through one typed surface. | Proposed | 2026-10-27 |",
		);
		expect(page.missing).toEqual([64]);
	});

	test("escapes a pipe so a title cannot break the table", () => {
		const odd = renderDecisionsPage(
			[{ ...decisions[1], title: "A | B" } as never],
			{ 25: "Uses | too." },
			{ repository: "https://github.com/o/r" },
		);
		expect(odd.content).toContain("| A \\| B | Uses \\| too. |");
	});
});
