/**
 * The install counts, read from the JSON `scripts/generate.ts` fetches.
 *
 * A registry that did not answer leaves `null` behind, and the cell renders a
 * dash: the table is the page's evidence, not its prerequisite, so a quiet
 * registry API must not take the page down with it.
 */
import stats from "@/lib/generated/stats.json";

interface Row {
	readonly registry: string;
	readonly package: string;
	readonly url: string;
	readonly lastMonth: number | null;
}

const formatter = new Intl.NumberFormat("en");

export function RegistryStats() {
	const rows = (stats as { rows: readonly Row[] }).rows;
	return (
		<table>
			<thead>
				<tr>
					<th>Registry</th>
					<th>Package</th>
					<th>Downloads, last 30 days</th>
				</tr>
			</thead>
			<tbody>
				{rows.map((row) => (
					<tr key={`${row.registry}:${row.package}`}>
						<td>{row.registry}</td>
						<td>
							<a href={row.url}>
								<code>{row.package}</code>
							</a>
						</td>
						<td>
							{row.lastMonth === null ? "-" : formatter.format(row.lastMonth)}
						</td>
					</tr>
				))}
			</tbody>
		</table>
	);
}
