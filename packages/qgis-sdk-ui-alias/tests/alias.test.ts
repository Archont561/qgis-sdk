import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

// The alias is one line per entry point and a manifest; what can go wrong is
// drift: an entry the scoped package gained or lost, a version the release
// stamp forgot, a peer the scoped package changed. These tests pin the alias
// to the scoped package file for file, so the drift fails here rather than in
// a consumer's bundler (the shape of the bridge alias, decision-33).

const ALIAS_ROOT = join(import.meta.dir, "..");
const SCOPED_ROOT = join(ALIAS_ROOT, "..", "qgis-sdk-ui");
const SCOPED_NAME = "@archont561/qgis-sdk-ui";

type Manifest = {
	name: string;
	version: string;
	exports: Record<string, Record<string, string> | string>;
	files: string[];
	dependencies?: Record<string, string>;
	peerDependencies?: Record<string, string>;
	peerDependenciesMeta?: Record<string, { optional?: boolean }>;
};

const readManifest = (root: string): Manifest =>
	JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as Manifest;

const alias = readManifest(ALIAS_ROOT);
const scoped = readManifest(SCOPED_ROOT);

const isStylesheet = (subpath: string): boolean => subpath.endsWith(".css");

const entryName = (subpath: string): string =>
	subpath === "." ? "index" : subpath.slice("./".length);

const reexportLine = (subpath: string): string =>
	`export * from "${SCOPED_NAME}${subpath === "." ? "" : subpath.slice(1)}";\n`;

const importLine = (subpath: string): string =>
	`@import "${SCOPED_NAME}${subpath.slice(1)}";\n`;

describe("the qgis-sdk-ui alias mirrors @archont561/qgis-sdk-ui", () => {
	test("it is the unscoped name of the scoped package", () => {
		expect(alias.name).toBe("qgis-sdk-ui");
		expect(scoped.name).toBe(SCOPED_NAME);
	});

	test("it carries the scoped version and pins the dependency to it exactly", () => {
		expect(alias.version).toBe(scoped.version);
		expect(alias.dependencies).toEqual({ [SCOPED_NAME]: scoped.version });
	});

	test("it exposes exactly the scoped entry points", () => {
		expect(Object.keys(alias.exports).sort()).toEqual(
			Object.keys(scoped.exports).sort(),
		);
	});

	test.each(Object.keys(scoped.exports).filter((s) => !isStylesheet(s)))(
		"%s re-exports its scoped entry",
		(subpath) => {
			const entry = entryName(subpath);
			expect(alias.exports[subpath]).toEqual({
				types: `./${entry}.d.ts`,
				import: `./${entry}.js`,
				default: `./${entry}.js`,
			});
			for (const extension of [".js", ".d.ts"]) {
				const file = join(ALIAS_ROOT, `${entry}${extension}`);
				expect(existsSync(file)).toBe(true);
				expect(readFileSync(file, "utf8")).toBe(reexportLine(subpath));
			}
			// The specifier it forwards to is an entry the scoped package builds.
			expect(existsSync(join(SCOPED_ROOT, "src", `${entry}.ts`))).toBe(true);
		},
	);

	test.each(Object.keys(scoped.exports).filter(isStylesheet))(
		"%s imports the scoped stylesheet",
		(subpath) => {
			const file = subpath.slice("./".length);
			expect(alias.exports[subpath]).toBe(`./${file}`);
			expect(readFileSync(join(ALIAS_ROOT, file), "utf8")).toBe(
				importLine(subpath),
			);
		},
	);

	test("it ships every re-export file and nothing else", () => {
		expect(alias.files).toEqual([
			"*.js",
			"*.d.ts",
			"*.css",
			"README.md",
			"LICENSE",
		]);
		expect(readFileSync(join(ALIAS_ROOT, "LICENSE"), "utf8")).toBe(
			readFileSync(join(SCOPED_ROOT, "LICENSE"), "utf8"),
		);
	});

	test("it declares the scoped package's optional peers, so ./react warns the same way", () => {
		expect(alias.peerDependencies).toEqual(scoped.peerDependencies);
		expect(alias.peerDependenciesMeta).toEqual(scoped.peerDependenciesMeta);
	});
});
