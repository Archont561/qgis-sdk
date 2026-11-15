/**
 * The directive layer: components written as plain text in a guide source and
 * expanded by the generator.
 *
 * The guide sources under `apps/docs/guides` are the canonical explanation and
 * are read on GitHub (decision-29), so they cannot carry JSX: an MDX page would
 * render it, but the same file opened as markdown shows a wall of tags, and a
 * `.md` page silently drops it. The middle path is a block syntax that reads as
 * text on GitHub and is expanded into JSX for the emitted `.mdx`:
 *
 * ```text
 * :::callout type=warning title="Before you start"
 * Body, in markdown.
 * :::
 *
 * :::steps
 * 1. First step, with a fence if it needs one.
 * 2. Second step.
 * :::
 *
 * :::tabs
 * :::tab pip
 * The pip path.
 * :::
 * :::tab pixi
 * The pixi path.
 * :::
 * :::
 *
 * :::files
 * - my-plugin/
 *   - plugin.py
 * :::
 *
 * :::accordions
 * :::accordion title="Why a callback?"
 * The answer.
 * :::
 * :::
 * ```
 *
 * Every block opens with `:::name` and closes with a bare `:::`; `tabs` and
 * `accordions` are the only blocks that contain other blocks. A fence is
 * literal, so a directive can be documented inside one. Anything else - an
 * unknown name, a directive inside a block that takes text, a block left open -
 * is an error with its line number, because a directive that is silently left
 * alone renders as `:::steps` in the middle of a page.
 *
 * The expansion wraps each component in `<div data-qgis-sdk="name">`. That
 * wrapper is the build gate's evidence: `scripts/lib/gate.ts` checks the
 * exported HTML for the marker of every directive a page used, which is how a
 * page that renders without its components is caught instead of shipped.
 */

/** A directive block, as parsed: its name, the rest of its line, its content. */
export interface Block {
	readonly name: string;
	/** Everything after the name on the opening line, trimmed. */
	readonly argument: string;
	/** 1-based line of the opening marker, for an error a reader can find. */
	readonly line: number;
	/** The text between the markers, one entry per line. */
	readonly text: readonly string[];
	/** Nested blocks; only `tabs` and `accordions` may have any. */
	readonly children: readonly Block[];
}

/** A run of ordinary markdown, or a directive that became JSX. */
type Node_ =
	| { readonly kind: "text"; readonly lines: readonly string[] }
	| { readonly kind: "block"; readonly block: Block };

/** What an expansion produced: the markdown, and the components it used. */
export interface Expansion {
	readonly markdown: string;
	/** Directive names, in the order they appear, deduplicated. */
	readonly components: readonly string[];
}

/** The parent each block must sit in; absent means "at the top level only". */
const PARENTS: Readonly<Record<string, string>> = {
	tab: "tabs",
	accordion: "accordions",
};

/** A draft block while its closing marker has not been seen. */
interface Draft {
	name: string;
	argument: string;
	line: number;
	text: string[];
	children: Block[];
}

const OPEN = /^:::[ \t]*([a-zA-Z-]+)((?:[ \t]+.*)?)$/;
const CLOSE = /^:::[ \t]*$/;
const FENCE = /^[ \t]*(`{3,}|~{3,})/;

/** A directive the expander cannot honour; the message names the line. */
export class DirectiveError extends Error {
	constructor(line: number, message: string) {
		super(line === 0 ? message : `directive on line ${line}: ${message}`);
		this.name = "DirectiveError";
	}
}

/** Where the next text line or finished block goes. */
interface Target {
	readonly root: Node_[];
	readonly stack: Draft[];
	readonly tail: { lines: string[] | null };
}

function appendText(target: Target, line: string): void {
	const top = target.stack[target.stack.length - 1];
	if (top !== undefined) {
		top.text.push(line);
		return;
	}
	if (target.tail.lines === null) {
		target.tail.lines = [];
		target.root.push({ kind: "text", lines: target.tail.lines });
	}
	target.tail.lines.push(line);
}

/** A block finished: hand it to its parent, or to the document. */
function appendBlock(target: Target, block: Block): void {
	const parent = target.stack[target.stack.length - 1];
	const expected = PARENTS[block.name];
	if (expected === undefined) {
		if (parent !== undefined) {
			throw new DirectiveError(
				block.line,
				`:::${block.name} cannot sit inside :::${parent.name}; ` +
					"only tabs and accordions hold other blocks",
			);
		}
		target.root.push({ kind: "block", block });
		target.tail.lines = null;
		return;
	}
	if (parent === undefined || parent.name !== expected) {
		throw new DirectiveError(
			block.line,
			`:::${block.name} belongs in :::${expected}, not at the top level` +
				(parent === undefined ? "" : ` or inside :::${parent.name}`),
		);
	}
	parent.children.push(block);
}

/** Read one line of the source into the tree being built. */
function consume(target: Target, line: string, number: number): void {
	const opened = OPEN.exec(line);
	if (opened !== null) {
		target.stack.push({
			name: opened[1] ?? "",
			argument: (opened[2] ?? "").trim(),
			line: number,
			text: [],
			children: [],
		});
		return;
	}
	if (CLOSE.test(line)) {
		const draft = target.stack.pop();
		if (draft === undefined) {
			throw new DirectiveError(
				number,
				"`:::` closes a block that was never opened",
			);
		}
		appendBlock(target, { ...draft });
		return;
	}
	appendText(target, line);
}

/** Split a source into text runs and blocks, fences and all. */
function parse(markdown: string): readonly Node_[] {
	const target: Target = { root: [], stack: [], tail: { lines: null } };
	let fence: string | null = null;
	markdown.split("\n").forEach((line, index) => {
		const number = index + 1;
		if (fence !== null) {
			appendText(target, line);
			if (line.trim().startsWith(fence)) fence = null;
			return;
		}
		const opened = FENCE.exec(line);
		if (opened !== null) {
			fence = opened[1] ?? "```";
			appendText(target, line);
			return;
		}
		consume(target, line, number);
	});
	const unclosed = target.stack[target.stack.length - 1];
	if (unclosed !== undefined) {
		throw new DirectiveError(
			unclosed.line,
			`:::${unclosed.name} is never closed`,
		);
	}
	return target.root;
}

/** `name=value` pairs and bare words, as a directive's opening line holds them. */
interface Attributes {
	readonly values: ReadonlyMap<string, string>;
	readonly words: readonly string[];
}

/** Split an opening line into words, keeping a quoted segment in one piece. */
function tokens(argument: string): readonly string[] {
	const out: string[] = [];
	let current = "";
	let quote: string | null = null;
	let escaped = false;
	for (const character of argument) {
		if (escaped) {
			current += character;
			escaped = false;
			continue;
		}
		if (character === "\\" && quote !== null) {
			current += character;
			escaped = true;
			continue;
		}
		if (quote !== null) {
			current += character;
			if (character === quote) quote = null;
			continue;
		}
		if (character === '"' || character === "'") {
			quote = character;
			current += character;
			continue;
		}
		if (/\s/.test(character)) {
			if (current !== "") out.push(current);
			current = "";
			continue;
		}
		current += character;
	}
	if (current !== "") out.push(current);
	return out;
}

/** Drop the quotes a value arrived in, and the escapes they protect. */
function unquote(value: string): string {
	const quoted = /^"(.*)"$/s.exec(value) ?? /^'(.*)'$/s.exec(value);
	const inner = quoted?.[1];
	if (inner === undefined) return value;
	return inner.replace(/\\(["'\\])/g, "$1");
}

function parseAttributes(argument: string): Attributes {
	const values = new Map<string, string>();
	const words: string[] = [];
	for (const token of tokens(argument)) {
		const pair = /^([a-zA-Z-]+)=([\s\S]*)$/.exec(token);
		if (pair === null) {
			words.push(unquote(token));
			continue;
		}
		values.set(pair[1] ?? "", unquote(pair[2] ?? ""));
	}
	return { values, words };
}

/** A JSX string literal for an attribute value. */
function quoted(value: string): string {
	return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

/** `body` wrapped in the marker the build gate looks for in the HTML. */
function tagged(name: string, body: string): string {
	return `<div data-qgis-sdk=${quoted(name)}>\n${body}\n</div>`;
}

/** A block's text, trimmed of the blank lines its markers add. */
function bodyOf(block: Block): string {
	return block.text.join("\n").replace(/^\n+/, "").replace(/\s+$/, "");
}

/** A block that holds text must not also hold a directive. */
function assertNoChildren(block: Block): void {
	const child = block.children[0];
	if (child !== undefined) {
		throw new DirectiveError(
			child.line,
			`:::${child.name} cannot sit inside :::${block.name}`,
		);
	}
}

function required(block: Block, name: string, hint: string): string {
	const value = parseAttributes(block.argument).values.get(name);
	if (value === undefined || value === "") {
		throw new DirectiveError(block.line, hint);
	}
	return value;
}

const CALLOUT_TYPES = ["info", "warning", "error", "success", "idea"];

function renderCallout(block: Block): string {
	assertNoChildren(block);
	const attributes = parseAttributes(block.argument);
	const type = attributes.values.get("type") ?? "info";
	if (CALLOUT_TYPES.includes(type) === false) {
		throw new DirectiveError(
			block.line,
			`unknown callout type ${type}; use ${CALLOUT_TYPES.join(", ")}`,
		);
	}
	const title = attributes.values.get("title");
	const opening =
		title === undefined
			? `<Callout type=${quoted(type)}>`
			: `<Callout type=${quoted(type)} title=${quoted(title)}>`;
	return tagged("callout", `${opening}\n\n${bodyOf(block)}\n\n</Callout>`);
}

/** Remove the indentation a list item's continuation lines carry. */
function dedent(text: string): string {
	const [, ...rest] = text.split("\n");
	const widths = rest
		.filter((line) => line.trim() !== "")
		.map((line) => /^[ \t]*/.exec(line)?.[0].length ?? 0);
	const width = widths.length === 0 ? 0 : Math.min(...widths);
	return [
		text.split("\n")[0] ?? "",
		...rest.map((line) => line.slice(width)),
	].join("\n");
}

/** The top-level items of an ordered list, with their continuation lines. */
function numberedItems(block: Block): readonly string[] {
	const items: string[] = [];
	for (const text of block.text) {
		if (/^\d+[.)][ \t]/.test(text)) {
			items.push(text.replace(/^\d+[.)][ \t]+/, ""));
			continue;
		}
		const last = items.length - 1;
		if (last < 0) {
			if (text.trim() === "") continue;
			throw new DirectiveError(
				block.line,
				":::steps holds an ordered list; start each step with `1.`",
			);
		}
		items[last] = `${items[last]}\n${text}`;
	}
	if (items.length === 0) {
		throw new DirectiveError(block.line, ":::steps has no steps");
	}
	return items.map((item) => dedent(item).trim());
}

function renderSteps(block: Block): string {
	assertNoChildren(block);
	const steps = numberedItems(block).map(
		(step) => `<Step>\n\n${step}\n\n</Step>`,
	);
	return tagged("steps", `<Steps>\n${steps.join("\n")}\n</Steps>`);
}

/** One entry of a `:::files` tree: a name, whether it is a folder, its depth. */
interface TreeEntry {
	readonly name: string;
	readonly folder: boolean;
	readonly depth: number;
}

function parseTree(block: Block): readonly TreeEntry[] {
	const entries: TreeEntry[] = [];
	for (const text of block.text) {
		if (text.trim() === "") continue;
		const bullet = /^([ \t]*)[-*][ \t]+(\S.*)$/.exec(text);
		if (bullet === null) {
			throw new DirectiveError(
				block.line,
				`:::files holds a bullet tree; ${JSON.stringify(text)} is not one`,
			);
		}
		const indent = (bullet[1] ?? "").replace(/\t/g, "  ").length;
		if (indent % 2 !== 0) {
			throw new DirectiveError(block.line, ":::files indents by two spaces");
		}
		const name = (bullet[2] ?? "").trim();
		entries.push({
			name: name.replace(/\/$/, ""),
			folder: name.endsWith("/"),
			depth: indent / 2,
		});
	}
	if (entries.length === 0) {
		throw new DirectiveError(block.line, ":::files is empty");
	}
	return entries;
}

/** Where a tree render stands: the entries, the cursor, the block for errors. */
interface TreeCursor {
	readonly entries: readonly TreeEntry[];
	readonly block: Block;
	index: number;
}

function renderTree(cursor: TreeCursor, depth: number): readonly string[] {
	const out: string[] = [];
	while (cursor.index < cursor.entries.length) {
		const entry = cursor.entries[cursor.index] as TreeEntry;
		if (entry.depth < depth) break;
		if (entry.depth > depth) {
			throw new DirectiveError(
				cursor.block.line,
				`:::files indents ${entry.name} too deep`,
			);
		}
		cursor.index += 1;
		const children = renderTree(cursor, depth + 1);
		out.push(
			children.length > 0 || entry.folder
				? `<Folder name=${quoted(entry.name)} defaultOpen>\n${children.join("\n")}\n</Folder>`
				: `<File name=${quoted(entry.name)} />`,
		);
	}
	return out;
}

function renderFiles(block: Block): string {
	assertNoChildren(block);
	const entries = parseTree(block);
	const rendered = renderTree({ entries, block, index: 0 }, 0);
	return tagged("files", `<Files>\n${rendered.join("\n")}\n</Files>`);
}

/** The label a `:::tab` or `:::accordion` carries: `label=pip` or `pip`. */
function labelOf(block: Block, name: string): string {
	const attributes = parseAttributes(block.argument);
	const value = attributes.values.get("label") ?? attributes.values.get(name);
	if (value !== undefined && value !== "") return value;
	const word = attributes.words[0];
	if (word !== undefined && word !== "") return word;
	throw new DirectiveError(
		block.line,
		`:::${block.name} needs a label, e.g. \`:::${block.name} pip\``,
	);
}

function renderTab(block: Block): string {
	assertNoChildren(block);
	const label = labelOf(block, "label");
	return `<Tab value=${quoted(label)}>\n\n${bodyOf(block)}\n\n</Tab>`;
}

function onlyChildren(block: Block, child: string): readonly Block[] {
	const stray = block.text.find((line) => line.trim() !== "");
	if (stray !== undefined) {
		throw new DirectiveError(
			block.line,
			`:::${block.name} holds only :::${child} blocks`,
		);
	}
	if (block.children.length === 0) {
		throw new DirectiveError(
			block.line,
			`:::${block.name} has no :::${child} blocks`,
		);
	}
	return block.children;
}

function renderTabs(block: Block): string {
	const tabs = onlyChildren(block, "tab");
	const labels = tabs.map((tab) => labelOf(tab, "label"));
	const items = `[${labels.map((label) => quoted(label)).join(", ")}]`;
	return tagged(
		"tabs",
		`<Tabs items={${items}} defaultValue=${quoted(labels[0] ?? "")}>\n${tabs
			.map(renderTab)
			.join("\n")}\n</Tabs>`,
	);
}

/** A heading-like id for an accordion, so its anchor can be linked. */
function anchor(value: string): string {
	return value
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/^-+|-+$/g, "");
}

function renderAccordion(block: Block): string {
	assertNoChildren(block);
	const title = required(
		block,
		"title",
		':::accordion needs a title, e.g. title="Why?"',
	);
	const id = parseAttributes(block.argument).values.get("id") ?? anchor(title);
	return tagged(
		"accordion",
		`<Accordion title=${quoted(title)} id=${quoted(id)}>\n\n${bodyOf(block)}\n\n</Accordion>`,
	);
}

function renderAccordions(block: Block): string {
	const accordions = onlyChildren(block, "accordion");
	return tagged(
		"accordions",
		`<Accordions>\n${accordions.map(renderAccordion).join("\n")}\n</Accordions>`,
	);
}

/** The renderer per directive name, and the name the HTML is tagged with. */
const RENDERERS: Readonly<Record<string, (block: Block) => string>> = {
	accordion: renderAccordion,
	accordions: renderAccordions,
	callout: renderCallout,
	files: renderFiles,
	steps: renderSteps,
	tab: renderTab,
	tabs: renderTabs,
};

/** Render one block, checking the name is one this layer knows. */
function renderBlock(block: Block, used: string[]): string {
	const renderer = RENDERERS[block.name];
	if (renderer === undefined) {
		throw new DirectiveError(
			block.line,
			`unknown directive :::${block.name}; the layer knows ` +
				["callout", "steps", "tabs", "files", "accordions"].join(", "),
		);
	}
	for (const name of [
		block.name,
		...block.children.map((child) => child.name),
	]) {
		if (used.includes(name) === false) used.push(name);
	}
	return renderer(block);
}

/**
 * Expand every directive in `markdown`, leaving the rest untouched.
 *
 * Returns the components the page now uses so the generator can record them:
 * that record is what the build gate compares the exported HTML against.
 */
export function expandDirectives(markdown: string): Expansion {
	const nodes = parse(markdown);
	if (nodes.some((node) => node.kind === "block") === false) {
		return { markdown, components: [] };
	}
	const used: string[] = [];
	const parts = nodes.map((node) =>
		node.kind === "text"
			? node.lines.join("\n")
			: renderBlock(node.block, used),
	);
	return { markdown: parts.join("\n"), components: used };
}

/**
 * Replace every directive block with its body, dropping the markers.
 *
 * Used where a page needs the text without the components: the frontmatter
 * description is the page's first sentence, and a `:::` line is not one.
 */
export function directiveText(markdown: string): string {
	const nodes = parse(markdown);
	if (nodes.some((node) => node.kind === "block") === false) return markdown;
	return nodes
		.map((node) =>
			node.kind === "text" ? node.lines.join("\n") : bodyOf(node.block),
		)
		.join("\n");
}
