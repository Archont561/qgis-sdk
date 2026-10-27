/**
 * The elements, loaded after the window: every test file imports this
 * module dynamically once `install()` has run, and gets the registered
 * catalogue plus a `mount` that renders a template into a fresh container.
 */

import { render, type TemplateResult } from "lit";
import * as ui from "../../src/index";
import { container, tick } from "./dom";

ui.defineElements();

export { ui };

/** Render `template` into a new container and let the first update land. */
export async function mount(template: TemplateResult): Promise<HTMLElement> {
	const root = container();
	render(template, root);
	await tick();
	return root;
}

/** The one element of `tag` under `root`, typed as the caller says. */
export function one<T extends Element>(root: ParentNode, selector: string): T {
	const found = root.querySelector<T>(selector);
	if (found === null) {
		throw new Error(`no ${selector} under the container`);
	}
	return found;
}

/** Fire `input` (and `change`) on a control after setting its value. */
export function type(control: HTMLInputElement, value: string): void {
	control.value = value;
	control.dispatchEvent(new Event("input", { bubbles: true }));
}

/** Pick an option of a select by value and fire `change`. */
export function choose(control: HTMLSelectElement, value: string): void {
	control.value = value;
	control.dispatchEvent(new Event("change", { bubbles: true }));
}
