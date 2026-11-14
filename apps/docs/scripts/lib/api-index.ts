/**
 * The API index: one page listing every stable Python name this release
 * promises, grouped by module.
 *
 * The facts come from `api/python.json`, which `qgis-sdk api dump` writes and
 * `release.py verify-api` diffs between releases - the same document the
 * stability table in the Python guide is pasted from and `check`'s rule
 * catalogue is built on. Nothing here is transcribed: a name that leaves the
 * inventory leaves the page on the next build, and a name that joins it cannot
 * be missing from the page.
 *
 * Two editorial parts live beside this module, not in it:
 *
 * - `scripts/api-modules.ts` says, per module, one sentence of what it is and
 *   which guide section explains it. A module without an entry is reported
 *   rather than silently rendered with no prose.
 * - The routes are resolved by the caller, because only it has the rendered
 *   guides: a section heading becomes a page slug through `splitGuide`, and a
 *   heading that no longer exists is reported instead of becoming a dead link.
 */

export interface InventoryModule {
	/** `stable`, `evolving` or `internal`; the tier the module declares. */
	readonly tier: string;
	/** Every public name, mapped to its normalised signature or its type. */
	readonly names: Readonly<Record<string, string>>;
}

export interface InventoryDeprecation {
	readonly module: string;
	readonly name: string;
	readonly since: string;
	readonly removal: string;
	readonly use: string;
}

export interface Inventory {
	readonly api_version: number;
	readonly modules: Readonly<Record<string, InventoryModule>>;
	readonly rules: readonly string[];
	readonly cli: readonly string[];
	readonly host_operations: readonly string[];
	readonly deprecations: readonly InventoryDeprecation[];
}

/** The guide section that explains a module, keyed by its heading. */
export interface ModuleSection {
	/** A `GUIDES` id, e.g. `doc-12`. */
	readonly guide: string;
	/** The `##` heading as the guide spells it. */
	readonly heading: string;
}

export interface ModuleNote {
	/** One sentence: what the module is for, in a reader's terms. */
	readonly description: string;
	/** Where the narrative explanation is, when the guide has one. */
	readonly section?: ModuleSection;
}

export type ModuleNotes = Readonly<Record<string, ModuleNote>>;

export interface ApiIndexInput {
	readonly inventory: Inventory;
	readonly notes: ModuleNotes;
	/** `guide id:heading` to the route of the page that holds it. */
	readonly routes: ReadonlyMap<string, string>;
}

export interface ApiIndexPage {
	readonly content: string;
	/** Public names the page lists, across every module. */
	readonly names: number;
	/** Modules in the inventory with no note in `scripts/api-modules.ts`. */
	readonly undescribed: readonly string[];
	/** Notes whose section is not a heading of the guide they name. */
	readonly unresolved: readonly string[];
}

const INTRO = `Every public name this release promises, in one place: one section per
module, and inside each the names it carries with the shape they have. It is the
index, not the tutorial - the guide explains what a name is for and when to reach
for it, and this page answers "does \`X\` exist, and what does it take".`;

const READING = `A row's shape is the normalised signature \`qgis-sdk api dump\`
records: defaults are written out, keyword-only arguments follow \`*\`, and a
constant shows the type it is annotated with rather than its value. \`class\`
means a name with no signature of its own - a service Protocol or an exception -
so there is nothing to pass it. Nothing here
is typed by hand - the page is rendered from \`api/python.json\` on every build,
and that document is what \`release.py verify-api\` diffs between releases. A
module that gains a name gains a row; a name that is removed loses one.

The tier is what a name costs to change
([decision-56](/reference/design-decisions/#decision-56)): a stable name may be
renamed, lose an argument or change what it returns only in a major after 1.0,
and in a documented minor before it. \`dev.*\`, the agent tools and \`release.py\`
are *evolving* and say so in the release notes; \`qgis_sdk.adapters\`, the inside
of \`qgis_sdk.bridge\` and anything underscored are *internal* and absent from this
page, because they are not a promise.`;

/** A table cell: one line, and a pipe cannot end the cell early. */
function cell(text: string): string {
	return text.split("\n").join(" ").split("|").join("\\|").trim();
}

function rows(names: Readonly<Record<string, string>>): string[] {
	return Object.keys(names)
		.sort()
		.map((name) => {
			// A Protocol or an exception has no constructor signature to print;
			// `class` says so without leaving an empty cell.
			const shape = (names[name] ?? "").trim();
			return `| \`${cell(name)}\` | \`${cell(shape === "" ? "class" : shape)}\` |`;
		});
}

export function renderApiIndex(input: ApiIndexInput): ApiIndexPage {
	const modules = Object.keys(input.inventory.modules).sort();
	const undescribed: string[] = [];
	const unresolved: string[] = [];
	const blocks: string[] = [];
	let total = 0;

	for (const name of modules) {
		const module = input.inventory.modules[name];
		if (module === undefined) {
			continue;
		}
		const note = input.notes[name];
		if (note === undefined) {
			undescribed.push(name);
		}
		let explanation = "";
		const section = note?.section;
		if (section !== undefined) {
			const key = `${section.guide}:${section.heading}`;
			const route = input.routes.get(key);
			if (route === undefined) {
				unresolved.push(key);
			} else {
				explanation = ` Explained in [${section.heading}](${route}/).`;
			}
		} else if (note !== undefined) {
			explanation = " No guide section introduces this module yet.";
		}
		const counted = Object.keys(module.names).length;
		total += counted;
		blocks.push(
			[
				`## \`${name}\``,
				"",
				`${note?.description ?? "No note."}${explanation}`,
				"",
				`Tier \`${module.tier}\`: ${counted} names.`,
				"",
				"| Name | Shape |",
				"| :-- | :-- |",
				...rows(module.names),
				"",
			].join("\n"),
		);
	}

	const cli = input.inventory.cli.length;
	const rules = input.inventory.rules.length;
	const operations = input.inventory.host_operations.length;
	const deprecated = input.inventory.deprecations;
	const deprecationLine =
		deprecated.length === 0
			? `No name in this release carries a deprecation mark: the \`Deprecated\`
column of the [stability table](/python/stability/) is zero for every module, and
\`check\` has no \`API001\` finding to make.`
			: `**On its way out.** ${deprecated
					.map(
						(entry) =>
							`\`${entry.module}.${entry.name}\` (deprecated since ${entry.since}, removed in ${entry.removal}${entry.use === "" ? "" : `, use \`${entry.use}\``})`,
					)
					.join(", ")}. A use is \`API001\`, and \`release.py verify-api\`
refuses the removal before the version named here.`;

	const content = [
		"---",
		'title: "API index"',
		'description: "Every stable Python name this release promises, by module, with its signature - rendered from the inventory `verify-api` diffs between releases."',
		"---",
		INTRO,
		"",
		READING,
		"",
		deprecationLine,
		"",
		`## What this page does not list`,
		"",
		`Four surfaces are stable and documented where they are used rather than
here. The first three are keys of the same inventory, so a name added to one of
them is a change \`verify-api\` reports; the fourth is the package's \`exports\`
field, which the documentation gate reads:

- the ${cli} \`qgis-sdk\` commands and their flags, each described where it is
  used in the Python guide;
- the ${rules} check rule ids, one row each in
  [Project checks](/python/project-checks/);
- the ${operations} host operations a web view may call, in
  [WebEngine bridge, host side](/python/webengine-bridge-host-side/);
- the TypeScript package's seven subpaths, in
  [Exports](/typescript/exports/).`,
		"",
		...blocks,
	].join("\n");

	return { content, names: total, undescribed, unresolved };
}
