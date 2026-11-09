#!/usr/bin/env node
/**
 * Refresh the generated regions of AGENTS.md.
 *
 * `AGENTS.md` is two documents in one file. The rules an agent has to follow are
 * written by hand and never touched; the few lists that are facts about the
 * repository - what the project is, which directories exist, which branch is the
 * default - come from `agents-md`, which regenerates only the regions it owns
 * (the `agents-md:begin`/`agents-md:end` markers).
 *
 * The tool detects a JavaScript repository here, because the workspace root is a
 * `package.json`, and reports `npm` commands and a `node` stack. Neither is true:
 * the SDK is Python, the environments are Pixi, the JavaScript workspace is Bun.
 * So this wrapper runs the generator and then corrects the three places where its
 * detection is wrong for this tree, rather than leaving a tool's guess in a file
 * agents are told to trust.
 *
 *   bun run agents          rewrite AGENTS.md
 *   bun run agents:check    fail if it would change (CI)
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const target = join(root, "AGENTS.md");
const check = process.argv.includes("--check");

/** What the stack actually is; `agents-md` reads `package.json` and says node. */
const STACK =
	"Stack: Python 3.11-3.14 for the SDK (Pixi pins the environments), TypeScript for the bridge and the web components, Bun for the JavaScript workspace.";

/** Where the important code is; the generator leaves this as a TBD stub. */
const LAYOUT =
	"The SDK's suite is `packages/qgis-sdk-python/tests`; `apps/docs` is the documentation site; `backlog/` holds the task and decision records.";

const require = createRequire(join(root, "package.json"));
const cli = require.resolve("@eugeniughelbur/agents-md/bin/agents-md.js");

/** Run the generator over the checkout; it looks for the repository root itself. */
function generate() {
	execFileSync(process.execPath, [cli, "--no-symlink"], {
		cwd: root,
		stdio: ["ignore", "ignore", "inherit"],
	});
	return readFileSync(target, "utf8");
}

/** `git`, trimmed, in the checkout the wrapper was started from. */
function git(args) {
	return execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
}

/**
 * The default branch the repository declares, not the branch this checkout
 * happens to be on. A pull request is checked out detached, where
 * `git branch --show-current` says nothing; `origin/HEAD` is a clone's local
 * convenience that a CI checkout does not set. The answer has to be the same on
 * a runner and on a laptop, so it is read from the remote-tracking refs.
 */
function defaultBranch() {
	try {
		const head = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]);
		return head.replace(/^origin\//, "");
	} catch {
		// No `origin/HEAD` here; ask the remote-tracking refs instead.
	}
	for (const name of ["main", "master", "trunk"]) {
		try {
			git(["rev-parse", "--verify", "--quiet", `refs/remotes/origin/${name}`]);
			return name;
		} catch {
			// Not this one.
		}
	}
	throw new Error(
		"cannot tell which branch is the default; set refs/remotes/origin/HEAD",
	);
}

/** The body of a marked region, without its markers and its heading. */
function region(text, id) {
	const match = text.match(
		new RegExp(
			`<!-- agents-md:begin id=${id} -->\\n## [^\\n]+\\n([\\s\\S]*?)\\n<!-- agents-md:end id=${id} -->`,
		),
	);
	if (match === null) {
		throw new Error(`AGENTS.md has no '${id}' region for agents-md to own`);
	}
	return match[1];
}

function replaceRegion(text, id, body) {
	return text.replace(
		new RegExp(
			`(<!-- agents-md:begin id=${id} -->\\n## [^\\n]+\\n)[\\s\\S]*?(\\n<!-- agents-md:end id=${id} -->)`,
		),
		(_, head, end) => `${head}${body}${end}`,
	);
}

/** Drop the `_TBD: ..._` sentence the generator leaves when it cannot tell. */
function withoutStub(body) {
	return body.replace(/\s*_TBD:[^_]*_\s*/g, "").trim();
}

/**
 * The shape the rest of the tree's Markdown is held to: a blank line under a
 * heading, and no bare URL (`markdownlint-cli2` covers `AGENTS.md` too).
 */
function tidy(body) {
	const spaced = body.replace(/^(#{2,6} [^\n]+)\n(?=\S)/gm, "$1\n\n");
	return spaced.replace(/(?<![<(])(https?:\/\/[^\s)>]+)/g, "<$1>");
}

function normalize(text) {
	// The generator's overview is the `package.json` description followed by the
	// stack it guessed from the manifests. Keep the one, replace the other.
	const overview = region(text, "overview")
		.split(" Stack: ")[0]
		.trim()
		.replace(/_TBD:[^_]*_/g, "")
		.trim();
	const body = (text, id, content) =>
		replaceRegion(text, id, `\n${tidy(content)}`);
	let out = body(text, "overview", `${overview}\n\n${STACK}`);
	out = body(
		out,
		"structure",
		`${withoutStub(region(out, "structure"))}\n\n${LAYOUT}`,
	);
	const remote = git(["remote", "get-url", "origin"]).replace(/\.git$/, "");
	out = body(
		out,
		"git",
		`Default branch \`${defaultBranch()}\`. Remote: ${remote}`,
	);
	return out;
}

// The generator writes AGENTS.md itself, so what the file said before the run
// is what the result is compared against - and in `--check` the earlier content
// is put back, because a check that edits the tree is not a check.
const current = readFileSync(target, "utf8");
let refreshed;
try {
	refreshed = normalize(generate());
} catch (error) {
	// The generator writes the file itself, so a refresh that fails after it ran
	// would leave the raw, uncorrected sections behind.
	writeFileSync(target, current);
	throw error;
}

if (check) {
	writeFileSync(target, current);
	if (refreshed !== current) {
		console.error(
			"agents-md: AGENTS.md is stale; run `bun run agents` and commit the result",
		);
		process.exit(1);
	}
	console.log("agents-md: AGENTS.md is current");
	process.exit(0);
}

if (refreshed === current) {
	console.log("agents-md: AGENTS.md is current");
} else {
	writeFileSync(target, refreshed);
	console.log("agents-md: refreshed the generated regions of AGENTS.md");
}
