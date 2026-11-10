/**
 * The registry numbers the install page shows, fetched at build time.
 *
 * The page must never fail because a registry API is down, so every source is
 * optional: a request that errors, times out or answers in an unexpected shape
 * leaves its `null` in place and the component renders an em-free dash for it.
 * `STATS_OFFLINE=1` skips the requests entirely, which is what a test run and
 * an offline build use.
 */

export interface StatRow {
	readonly registry: string;
	readonly package: string;
	readonly url: string;
	/** Downloads in the last month, or `null` when the registry does not say. */
	readonly lastMonth: number | null;
}

export interface Stats {
	readonly generated: string;
	readonly rows: readonly StatRow[];
}

const TIMEOUT_MS = 4000;

const ROWS = [
	{
		registry: "PyPI",
		pkg: "qgis-sdk",
		url: "https://pypi.org/project/qgis-sdk/",
		api: "https://pypistats.org/api/packages/qgis-sdk/recent",
		pick: (body: unknown) => numberAt(body, "data", "last_month"),
	},
	{
		registry: "npm",
		pkg: "@archont561/qgis-sdk",
		url: "https://www.npmjs.com/package/@archont561/qgis-sdk",
		api: "https://api.npmjs.org/downloads/point/last-month/@archont561/qgis-sdk",
		pick: (body: unknown) => numberAt(body, "downloads"),
	},
	{
		registry: "npm",
		pkg: "@archont561/qgis-sdk-ui",
		url: "https://www.npmjs.com/package/@archont561/qgis-sdk-ui",
		api: "https://api.npmjs.org/downloads/point/last-month/@archont561/qgis-sdk-ui",
		pick: (body: unknown) => numberAt(body, "downloads"),
	},
	{
		registry: "prefix.dev",
		pkg: "qgis-sdk",
		url: "https://prefix.dev/channels/archont561/archont561",
		// prefix.dev publishes no download counts; the row stays, the number does not.
		api: null,
		pick: () => null,
	},
] as const;

function numberAt(body: unknown, ...path: string[]): number | null {
	let value: unknown = body;
	for (const key of path) {
		if (typeof value !== "object" || value === null || !(key in value)) {
			return null;
		}
		value = (value as Record<string, unknown>)[key];
	}
	return typeof value === "number" && Number.isFinite(value) ? value : null;
}

async function fetchRow(
	api: string | null,
	pick: (body: unknown) => number | null,
): Promise<number | null> {
	if (api === null || process.env.STATS_OFFLINE === "1") {
		return null;
	}
	try {
		const response = await fetch(api, {
			signal: AbortSignal.timeout(TIMEOUT_MS),
			headers: { accept: "application/json" },
		});
		if (!response.ok) {
			return null;
		}
		return pick(await response.json());
	} catch {
		return null;
	}
}

export async function collectStats(): Promise<Stats> {
	const rows = await Promise.all(
		ROWS.map(async (row) => ({
			registry: row.registry,
			package: row.pkg,
			url: row.url,
			lastMonth: await fetchRow(row.api, row.pick),
		})),
	);
	return { generated: new Date().toISOString(), rows };
}
