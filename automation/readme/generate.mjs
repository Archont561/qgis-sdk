#!/usr/bin/env node
/**
 * Regenerate the root README.md with readme-md-generator.
 *
 * The landing page is generated, not hand-maintained: `template.ejs` holds the
 * shape decision-29 settled on (a pitch, a status line, the package table, one
 * example, pointers and the license - `tests/scripts/test_readme_shape.py`
 * enforces that set) and pulls the repository URL, the homepage, the license
 * and the badges from `package.json`, so a moved repository or a renamed
 * license does not leave the README pointing at the old one.
 *
 * The generator asks before overwriting an existing README and its questions
 * are interactive, so the file is parked for the run and restored if the
 * generator fails: `bun run readme` is repeatable, and a broken run leaves the
 * tree as it was.
 */
import { execFileSync } from "node:child_process";
import { existsSync, renameSync, unlinkSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const template = join(here, "template.ejs");
const readme = join(root, "README.md");
const parked = join(tmpdir(), `qgis-sdk-readme-${process.pid}.md`);
const cli = createRequire(join(root, "package.json")).resolve(
	"readme-md-generator/src/index.js",
);

const hadReadme = existsSync(readme);
if (hadReadme) renameSync(readme, parked);

try {
	execFileSync(process.execPath, [cli, "-y", "-p", template], {
		cwd: root,
		stdio: "inherit",
	});
} catch (error) {
	if (hadReadme && existsSync(parked)) renameSync(parked, readme);
	console.error("readme: generation failed, README.md left as it was");
	process.exit(typeof error.status === "number" ? error.status : 1);
}

if (existsSync(parked)) unlinkSync(parked);
