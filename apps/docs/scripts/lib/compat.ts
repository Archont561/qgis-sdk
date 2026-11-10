/**
 * The version floor and ceiling the support matrix states, read from the matrix
 * itself so a landing-page sentence cannot drift from the qualification rows.
 *
 * The matrix lives in the Python reference guide between `support-matrix:begin`
 * and `support-matrix:end`; only the rows marked `qualified` count, because an
 * `unqualified` row is a combination the workspace has not demonstrated.
 */

export interface Compat {
	/** QGIS series with a qualified row, newest first. */
	readonly qgis: readonly { readonly series: string; readonly lts: boolean }[];
	/** Lowest and highest Python minor with a qualified row. */
	readonly python: { readonly min: string; readonly max: string };
	/** How many qualified rows the claim rests on. */
	readonly qualified: number;
}

const MATRIX =
	/<!-- support-matrix:begin -->([\s\S]*?)<!-- support-matrix:end -->/;
const SEPARATOR = /^\|\s*:?-+/;

function cells(line: string): string[] {
	return line
		.split("|")
		.slice(1, -1)
		.map((cell) => cell.trim());
}

function compare(left: string, right: string): number {
	const [a = 0, b = 0] = left.split(".").map(Number);
	const [c = 0, d = 0] = right.split(".").map(Number);
	return a - c || b - d;
}

export function collectCompat(guide: string): Compat {
	const block = MATRIX.exec(guide)?.[1] ?? "";
	const rows = block
		.split("\n")
		.map((line) => line.trim())
		.filter((line) => line.startsWith("|") && !SEPARATOR.test(line))
		.map(cells)
		// The header row is the one whose fourth cell says "QGIS".
		.filter((row) => row[3] !== "QGIS")
		.filter((row) => ["qualified", "unqualified"].includes(row[6] ?? ""));

	const qualified = rows.filter((row) => row[6] === "qualified");
	// The matrix says which row is the LTS in its own cells - the evidence
	// column names the CI job `QGIS 3.44 LTS` - so the label is read, not assumed.
	const bySeries = new Map<string, boolean>();
	for (const row of qualified) {
		const series = row[3] ?? "";
		if (series === "" || series === "-") {
			continue;
		}
		const lts = row.some((cell) => /\bLTS\b/.test(cell));
		bySeries.set(series, (bySeries.get(series) ?? false) || lts);
	}
	const qgis = [...bySeries.entries()]
		.map(([series, lts]) => ({ series, lts }))
		.sort((left, right) => compare(right.series, left.series));
	const pythons = qualified
		.map((row) => row[2] ?? "")
		.filter((value) => /^\d+\.\d+$/.test(value))
		.sort(compare);
	const min = pythons[0] ?? "";
	const max = pythons[pythons.length - 1] ?? "";
	return { qgis, python: { min, max }, qualified: qualified.length };
}
