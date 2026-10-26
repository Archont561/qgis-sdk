/**
 * The built package as a bundler sees it: which framework each entry point
 * reaches (TASK-69 AC #2).
 *
 * `bun run build` runs this after `bunup`. It walks `dist/*.js` through the
 * shared chunks and fails when an entry reaches a framework that is not its
 * own: a `./react`-only consumer must bundle no Vue and no Svelte, the root
 * and `./testing` none at all. The source-level test in `tests/surface.test.ts`
 * says the same of `src`; this one says it of what ships, where the chunk
 * splitter has the last word.
 */

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = resolve(
	dirname(fileURLToPath(import.meta.url)),
	"..",
	"..",
	"dist",
);
const IMPORT =
	/(?:^|[;\s])(?:import|export)\b[^;]*?\bfrom\s*["']([^"']+)["']|(?:^|[;\s])import\s*["']([^"']+)["']/gm;
const FRAMEWORKS = ["react", "vue", "svelte"] as const;
type Framework = (typeof FRAMEWORKS)[number];

/** What each entry may reach; every other framework is a failure. */
const ALLOWED: Record<string, readonly Framework[]> = {
	"index.js": [],
	"bridge.js": [],
	"host.js": [],
	"testing.js": [],
	"react.js": ["react"],
	"vue.js": ["vue"],
	"svelte.js": ["svelte"],
};

function importsOf(file: string): string[] {
	const code = readFileSync(file, "utf8");
	return [...code.matchAll(IMPORT)].map((m) => (m[1] ?? m[2]) as string);
}

function frameworkOf(specifier: string): Framework | null {
	for (const framework of FRAMEWORKS) {
		if (specifier === framework || specifier.startsWith(`${framework}/`)) {
			return framework;
		}
	}
	return null;
}

/** Every framework an entry reaches, following relative imports. */
function reaches(entry: string): Set<Framework> {
	const seen = new Set<string>();
	const found = new Set<Framework>();
	const queue = [entry];
	while (queue.length > 0) {
		const file = queue.pop() as string;
		if (seen.has(file)) {
			continue;
		}
		seen.add(file);
		for (const specifier of importsOf(file)) {
			if (specifier.startsWith(".")) {
				queue.push(resolve(dirname(file), specifier));
				continue;
			}
			const framework = frameworkOf(specifier);
			if (framework !== null) {
				found.add(framework);
			} else if (!specifier.startsWith("node:")) {
				throw new Error(
					`${file} imports ${specifier}, which is not a declared peer`,
				);
			}
		}
	}
	return found;
}

const entries = readdirSync(DIST).filter((name) => name.endsWith(".js"));
const failures: string[] = [];
for (const name of Object.keys(ALLOWED)) {
	if (!entries.includes(name)) {
		failures.push(`dist/${name} is missing`);
	}
}
for (const name of entries) {
	const allowed = ALLOWED[name];
	if (allowed === undefined) {
		failures.push(`dist/${name} is not a declared entry point`);
		continue;
	}
	const reached = reaches(join(DIST, name));
	const expected = new Set(allowed);
	for (const framework of reached) {
		if (!expected.has(framework)) {
			failures.push(`dist/${name} reaches ${framework}`);
		}
	}
	for (const framework of expected) {
		if (!reached.has(framework)) {
			failures.push(`dist/${name} no longer imports ${framework}`);
		}
	}
}

if (failures.length > 0) {
	console.error(`build output isolation failed:\n  ${failures.join("\n  ")}`);
	process.exit(1);
}
console.log(
	`build output isolation: ${entries.length} entries, each reaches its own framework only`,
);
