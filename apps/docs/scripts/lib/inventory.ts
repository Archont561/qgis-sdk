/**
 * Read the committed public API inventory, `api/python.json`.
 *
 * The document is written by `qgis-sdk api dump` and committed on purpose
 * (decision-56): the diff is what makes an added, renamed or removed public
 * name reviewable before it ships, and what `release.py verify-api` diffs one
 * tag against the next. The site only ever reads it, so the failure this module
 * owns is the boring one - a checkout without the file, or with a file that is
 * not the document.
 *
 * Paths are given as a build script has them: absolute, so the message names
 * the file a reader has to look at rather than a path relative to the caller.
 * Every message repeats the command that writes the file, because the JSON
 * parser's own complaint ("Unexpected end of JSON input") sends a reader
 * looking for a syntax bug in a file nobody edited by hand.
 */

import { readFile } from "node:fs/promises";
import type { Inventory } from "./api-index";

/** The sections `renderApiIndex` reads as lists; `modules` is checked apart. */
const LIST_SECTIONS = [
	"rules",
	"cli",
	"host_operations",
	"deprecations",
] as const;

/**
 * Whether a parsed document has the shape the renderer relies on.
 *
 * Only the top level is inspected: the renderer treats a module's `names` and a
 * deprecation's fields as data it may find empty, and a dump that got that far
 * is a dump. What this refuses is the wrong file entirely - a `{}`, a manifest,
 * a truncated write - before it becomes a `TypeError` somewhere down the page.
 */
function isInventory(document: unknown): document is Inventory {
	if (typeof document !== "object" || document === null) return false;
	const sections = document as Record<string, unknown>;
	if (typeof sections.api_version !== "number") return false;
	if (typeof sections.modules !== "object" || sections.modules === null) {
		return false;
	}
	return LIST_SECTIONS.every((name) => Array.isArray(sections[name]));
}

/** The inventory at `path`, or an error naming `qgis-sdk api dump`. */
export async function readInventory(path: string): Promise<Inventory> {
	let text: string;
	try {
		text = await readFile(path, "utf8");
	} catch {
		throw new Error(
			`${path}: no API inventory; run \`qgis-sdk api dump\` and commit it`,
		);
	}
	let document: unknown;
	try {
		document = JSON.parse(text);
	} catch (error) {
		throw new Error(
			`${path}: not JSON (${(error as Error).message}); run \`qgis-sdk api dump\``,
		);
	}
	if (!isInventory(document)) {
		throw new Error(
			`${path}: not an API inventory; run \`qgis-sdk api dump\` and commit the result`,
		);
	}
	return document;
}
