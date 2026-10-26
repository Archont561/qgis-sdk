/**
 * One happy-dom window for a test file, installed before any framework loads.
 *
 * Vue's DOM renderer and Svelte's mount read `document` when their modules
 * are evaluated, and Bun evaluates a package import before a relative one
 * whatever the source order. So a test file imports this module statically,
 * calls `install()`, and imports the framework (and the adapter that imports
 * it) dynamically, after it.
 *
 * `bun test` runs every file of a run in one process, so the globals must
 * not outlive the file: a global `window` makes json-schema-ref-parser (used
 * by contracts.test.ts) believe it is in a browser and read `location.href`.
 * Every file that calls `install()` registers `afterAll(uninstall)`; the
 * module is evaluated once per process, so installation is explicit.
 */

import { Window } from "happy-dom";

export const window: Window = new Window();

const INSTALLED = [
	"window",
	"document",
	"HTMLElement",
	"SVGElement",
	"Element",
	"Node",
	"Text",
	"Comment",
	"DocumentFragment",
	"navigator",
] as const;

const g = globalThis as Record<string, unknown>;
const w = window as unknown as Record<string, unknown>;
const previous = new Map<string, unknown>();

/** Put the window's globals on `globalThis`, remembering what was there. */
export function install(): void {
	for (const name of INSTALLED) {
		previous.set(name, g[name]);
		g[name] = name === "window" ? window : w[name];
	}
}

/** Put the globals back the way they were before `install()`. */
export function uninstall(): void {
	for (const name of INSTALLED) {
		const before = previous.get(name);
		if (before === undefined) {
			delete g[name];
		} else {
			g[name] = before;
		}
	}
	previous.clear();
}

/** A fresh container element attached to the document body. */
export function container(): HTMLElement {
	const element = window.document.createElement("div");
	window.document.body.appendChild(element);
	return element as unknown as HTMLElement;
}
