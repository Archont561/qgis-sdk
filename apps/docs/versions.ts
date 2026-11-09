/**
 * The versions the site describes, read from the workspace by
 * `scripts/generate.ts` and written to `lib/generated/versions.json`, which
 * the landing page imports. A bundled chunk cannot read the workspace from
 * its own location, so the read happens at generate time.
 */
import { readFileSync } from "node:fs";

const root = new URL("../../", import.meta.url);

function packageVersion(path: string): string {
	const manifest = JSON.parse(readFileSync(new URL(path, root), "utf8")) as {
		version: string;
	};
	return manifest.version;
}

function pyprojectVersion(path: string): string {
	const text = readFileSync(new URL(path, root), "utf8");
	const match = /^version\s*=\s*"([^"]+)"/m.exec(text);
	if (match?.[1] === undefined) {
		throw new Error(`no version in ${path}`);
	}
	return match[1];
}

export interface Versions {
	readonly python: string;
	readonly typescript: string;
	readonly ui: string;
}

export const versions: Versions = {
	python: pyprojectVersion("packages/qgis-sdk-python/pyproject.toml"),
	typescript: packageVersion("packages/qgis-sdk-typescript/package.json"),
	ui: packageVersion("packages/qgis-sdk-ui/package.json"),
};
