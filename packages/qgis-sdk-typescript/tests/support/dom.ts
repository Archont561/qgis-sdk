/**
 * One happy-dom window for a test file, installed before any framework loads.
 *
 * Vue's DOM renderer and Svelte's mount read `document` when their modules
 * are evaluated, and Bun evaluates a package import before a relative one
 * whatever the source order. So a test file imports this module statically
 * and the framework (and the adapter that imports it) dynamically, after it.
 */

import { Window } from "happy-dom";

export const window: Window = new Window();

const g = globalThis as Record<string, unknown>;
g.window = window;
g.document = window.document;
g.HTMLElement = window.HTMLElement;
g.SVGElement = window.SVGElement;
g.Element = window.Element;
g.Node = window.Node;
g.Text = window.Text;
g.Comment = window.Comment;
g.DocumentFragment = window.DocumentFragment;
g.navigator = window.navigator;

/** A fresh container element attached to the document body. */
export function container(): HTMLElement {
	const element = window.document.createElement("div");
	window.document.body.appendChild(element);
	return element as unknown as HTMLElement;
}
