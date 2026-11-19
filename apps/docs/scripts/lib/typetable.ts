/**
 * TypeTable content generated from the inventory (TASK-170 AC 7).
 *
 * A `TypeTable` is a Fumadocs component that renders a table of names, their
 * types and their descriptions. The content is not typed by hand and is not
 * produced through `fumadocs-typescript` (which needs built `.d.ts` files a
 * plain `next build` does not produce): it is rendered from the committed
 * `api/python.json` inventory, reusing the module note map the API index
 * already needs, so a stable name cannot lose its row.
 *
 * For one module, each public name becomes a row: the name, its normalised
 * shape (the signature `qgis-sdk api dump` records, or `class` for a name
 * with no signature of its own), the tier it costs to change, and the guide
 * section that explains it. The same function that renders a module's table
 * is what the completeness test runs over every module, so a name that leaves
 * the inventory leaves the table and a name that joins it cannot be missing.
 */

import type { Inventory, ModuleNotes } from "./api-index";

/** One row of a TypeTable, as the component reads it. */
export interface TypeNode {
	/** The normalised shape: the signature, or `class`. */
	readonly type: string;
	/** The tier and where the guide explains the name. */
	readonly description: string;
	/** The guide section that explains the name, as a link. */
	readonly typeDescriptionLink?: string;
}

/** The `type` prop of a `TypeTable`: name to its row. */
export type TypeTableData = Readonly<Record<string, TypeNode>>;

export interface TypeTableInput {
	readonly inventory: Inventory;
	readonly notes: ModuleNotes;
	/** `guide id:heading` to the route of the page that holds it. */
	readonly routes: ReadonlyMap<string, string>;
}

/** A name with no signature of its own: a Protocol or an exception. */
function shapeOf(signature: string): string {
	const shape = signature.trim();
	return shape === "" ? "class" : shape;
}

/**
 * The TypeTable data for one module: every public name, its shape, its tier
 * and the guide section that explains it.
 */
export function typeTableData(
	input: TypeTableInput,
	module: string,
): TypeTableData {
	const found = input.inventory.modules[module];
	if (found === undefined) {
		throw new Error(`typetable: ${module} is not in the inventory`);
	}
	const note = input.notes[module];
	let link: string | undefined;
	const section = note?.section;
	if (section !== undefined) {
		const route = input.routes.get(`${section.guide}:${section.heading}`);
		if (route !== undefined) {
			link = `${route}/`;
		}
	}
	const data: Record<string, TypeNode> = {};
	for (const name of Object.keys(found.names).sort()) {
		data[name] = {
			type: shapeOf(found.names[name] ?? ""),
			description: `Tier \`${found.tier}\`.`,
			...(link === undefined ? {} : { typeDescriptionLink: link }),
		};
	}
	return data;
}

/** Escape a string for a JSX attribute or a JS string in generated JSX. */
function jsString(value: string): string {
	return JSON.stringify(value);
}

/**
 * The `<TypeTable>` JSX for one module, with the data inline. The data is a
 * plain object literal, so the page needs no import of its own beyond the
 * registry the route already passes.
 */
export function renderTypeTable(input: TypeTableInput, module: string): string {
	const data = typeTableData(input, module);
	const rows = Object.entries(data)
		.map(([name, node]) => {
			const fields = [
				`type: ${jsString(node.type)}`,
				`description: ${jsString(node.description)}`,
			];
			if (node.typeDescriptionLink !== undefined) {
				fields.push(
					`typeDescriptionLink: ${jsString(node.typeDescriptionLink)}`,
				);
			}
			return `${jsString(name)}: { ${fields.join(", ")} }`;
		})
		.join(",\n");
	return `<TypeTable type={{${rows ? `\n${rows}\n` : ""}}} />`;
}

/**
 * Every stable name in the inventory, as `module.name`. The completeness
 * test holds the generated tables to this list.
 */
export function stableNames(inventory: Inventory): readonly string[] {
	const names: string[] = [];
	for (const [module, found] of Object.entries(inventory.modules)) {
		if (found.tier !== "stable") {
			continue;
		}
		for (const name of Object.keys(found.names)) {
			names.push(`${module}.${name}`);
		}
	}
	return names.sort();
}
