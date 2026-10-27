/**
 * One happy-dom window for a test file, installed before Lit loads.
 *
 * Lit reads `customElements`, `HTMLElement` and `document` when its modules
 * are evaluated, and Bun evaluates a package import before a relative one
 * whatever the source order. So a test file imports this module statically,
 * calls `install()`, and imports the elements dynamically, after it.
 *
 * `bun test` runs every file of a run in one process, so the globals must
 * not outlive the file: every file that calls `install()` registers
 * `afterAll(uninstall)`.
 */

import { Window } from "happy-dom";

export const window: Window = new Window();

const INSTALLED = [
	"window",
	"document",
	"Document",
	"HTMLTemplateElement",
	"customElements",
	"HTMLElement",
	"HTMLInputElement",
	"HTMLSelectElement",
	"HTMLButtonElement",
	"SVGElement",
	"Element",
	"Node",
	"Text",
	"Comment",
	"DocumentFragment",
	"ShadowRoot",
	"CSSStyleSheet",
	"Event",
	"CustomEvent",
	"KeyboardEvent",
	"MouseEvent",
	"InputEvent",
	"navigator",
	"requestAnimationFrame",
	"cancelAnimationFrame",
	"getComputedStyle",
] as const;

const g = globalThis as Record<string, unknown>;
const w = window as unknown as Record<string, unknown>;
const previous = new Map<string, unknown>();

/** Put the window's globals on `globalThis`, remembering what was there. */
export function install(): void {
	for (const name of INSTALLED) {
		previous.set(name, g[name]);
		const value = w[name];
		g[name] =
			name === "window"
				? window
				: typeof value === "function" && !/^[A-Z]/.test(name)
					? (value as (...args: unknown[]) => unknown).bind(window)
					: value;
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

/** Let Lit's microtask update cycle and queued replies land. */
export async function tick(times = 3): Promise<void> {
	for (let index = 0; index < times; index += 1) {
		await new Promise((resolve) => setTimeout(resolve, 0));
	}
}
