/**
 * `@archont561/qgis-sdk-ui/svelte`: the catalogue in Svelte 5.
 *
 * Svelte sets a property on a custom element when the element has one, so
 * a component writes `<qgis-layer-picker {qgis} {name} onqgis-change={...}>`
 * with no wrapper once the elements are registered. What this module adds
 * is the little Svelte asks for around that: registration on import, the
 * `qgisProps` action for a props object that changes as a whole (it assigns
 * each property and re-assigns on update, before and after upgrade), and
 * the event names typed. Svelte 5 or later is the peer.
 */

import type { ActionReturn } from "svelte/action";
import { EVENT_NAMES } from "./events";
import { defineElements } from "./index";

export type {
	QgisCancelEvent,
	QgisChangeEvent,
	QgisResultEvent,
	QgisRunEvent,
} from "./events";
export { EVENT_NAMES } from "./events";

if (typeof customElements !== "undefined") {
	defineElements();
}

/** The listener attribute names Svelte 5 spells the events as. */
export const ON: Readonly<Record<keyof typeof EVENT_NAMES, string>> =
	Object.freeze({
		change: `on${EVENT_NAMES.change}`,
		result: `on${EVENT_NAMES.result}`,
		run: `on${EVENT_NAMES.run}`,
		cancel: `on${EVENT_NAMES.cancel}`,
	});

/** Properties to assign; `undefined` leaves a property as it is. */
export type ElementProps = Readonly<Record<string, unknown>>;

/**
 * `use:qgisProps={props}`: assign every entry of `props` as an element
 * property, and again when `props` changes. Entries that are `undefined`
 * are skipped; an entry set to `null` is assigned.
 */
export function qgisProps(
	node: HTMLElement,
	props: ElementProps,
): ActionReturn<ElementProps> {
	const assign = (next: ElementProps): void => {
		const target = node as unknown as Record<string, unknown>;
		for (const [name, value] of Object.entries(next)) {
			if (value !== undefined && !Object.is(target[name], value)) {
				target[name] = value;
			}
		}
	};
	assign(props);
	return {
		update: assign,
	};
}
