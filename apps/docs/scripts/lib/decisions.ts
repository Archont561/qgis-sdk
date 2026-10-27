/**
 * The design-decisions page: one curated table over `backlog/decisions/`.
 *
 * The records themselves stay in the repository; the site publishes what a
 * user needs to understand a constraint they hit - number, title, a one-line
 * summary, status and date - and links each record from its number. Number,
 * title, status and date are read from the record's frontmatter at generate
 * time, so a status promotion in the backlog reaches the site on the next
 * build. The summary is the editorial part and lives in
 * `scripts/decision-summaries.ts`; a record without one falls back to its
 * title and is reported, so the gap is visible without breaking the build.
 */

export interface Decision {
	number: number;
	/** The record's file name under `backlog/decisions/`. */
	file: string;
	title: string;
	status: string;
	/** ISO date; the record's time of day is dropped. */
	date: string;
}

export interface DecisionsPage {
	content: string;
	/** Decision numbers that have no curated summary. */
	missing: number[];
}

const DECISIONS_DIR = "backlog/decisions";

/** The frontmatter block, as `key: value` pairs; folded scalars are joined. */
function frontmatterOf(markdown: string): Map<string, string> {
	const match = /^---\n([\s\S]*?)\n---(?:\n|$)/.exec(markdown);
	const fields = new Map<string, string>();
	if (!match) {
		return fields;
	}
	let key: string | null = null;
	let folded = false;
	for (const line of (match[1] ?? "").split("\n")) {
		const pair = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line);
		if (pair) {
			key = pair[1] ?? null;
			const value = (pair[2] ?? "").trim();
			folded =
				value === ">-" || value === ">" || value === "|" || value === "|-";
			fields.set(key ?? "", folded ? "" : unquote(value));
			continue;
		}
		if (key !== null && folded && /^\s+\S/.test(line)) {
			const current = fields.get(key) ?? "";
			fields.set(key, `${current}${current ? " " : ""}${line.trim()}`);
		}
	}
	return fields;
}

function unquote(value: string): string {
	const quoted = /^(['"])(.*)\1$/.exec(value);
	return quoted ? (quoted[2] ?? "") : value;
}

/** Parse one record; throws when a field the table needs is missing. */
export function parseDecision(file: string, markdown: string): Decision {
	const number = /^decision-(\d+)/.exec(file)?.[1];
	if (!number) {
		throw new Error(`${file}: not a decision record`);
	}
	const fields = frontmatterOf(markdown);
	const read = (name: string): string => {
		const value = fields.get(name);
		if (!value) {
			throw new Error(`${file}: frontmatter lacks ${name}`);
		}
		return value;
	};
	const date = read("date");
	return {
		number: Number(number),
		file,
		title: read("title"),
		status: read("status"),
		date: date.slice(0, 10),
	};
}

function cell(text: string): string {
	return text.replace(/\|/g, "\\|");
}

function capitalise(word: string): string {
	return word.charAt(0).toUpperCase() + word.slice(1);
}

const INTRO = `The SDK's architecture is recorded as decision records: short documents that
state a problem, the choice made and what it rules out. They are public
because the constraints they impose show up in the API - why a plugin never
sees \`iface\`, why a job is a plain function, why the two packages version
independently - and a user who hits one of those constraints deserves the
reasoning, not just the error.

Each row links the full record on GitHub from its number. The status is the
record's own: an *accepted* decision is in force, a *proposed* one is still
under discussion and not yet what a release does, and a *superseded* one has
been replaced by the later record its summary names. The date is when the
record was written.`;

/**
 * Render the page. `summaries` maps a decision number to one plain sentence;
 * the records are listed by number so the table is stable across builds.
 */
export function renderDecisionsPage(
	decisions: readonly Decision[],
	summaries: Readonly<Record<number, string>>,
	options: { repository: string },
): DecisionsPage {
	const ordered = [...decisions].sort((a, b) => a.number - b.number);
	const missing: number[] = [];
	const rows = ordered.map((decision) => {
		const summary = summaries[decision.number];
		if (!summary) {
			missing.push(decision.number);
		}
		const href = `${options.repository}/blob/main/${DECISIONS_DIR}/${encodeURIComponent(decision.file)}`;
		const id = `decision-${decision.number}`;
		return `| <a id="${id}" href="${href}">${id}</a> | ${cell(decision.title)} | ${cell(summary ?? `${decision.title}.`)} | ${capitalise(decision.status)} | ${decision.date} |`;
	});
	const content = [
		"---",
		'title: "Design decisions"',
		'description: "Every architecture decision behind the QGIS SDK in one table: what was decided, its status, and a link to the full record."',
		"sidebar:",
		"  order: 1",
		"---",
		INTRO,
		"",
		"| Number | Title | Decision | Status | Date |",
		"| :-- | :-- | :-- | :-- | :-- |",
		...rows,
		"",
	].join("\n");
	return { content, missing };
}
