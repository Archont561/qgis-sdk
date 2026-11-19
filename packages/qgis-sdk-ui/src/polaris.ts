/**
 * Shopify Polaris web components (decision-87).
 *
 * When a page loads the vendored `polaris-2.js` bundle, the `<s-*>` elements
 * are defined and the catalogue's elements render Polaris components instead
 * of native HTML controls. The properties, events, and store integration are
 * identical in both paths; only the rendering differs.
 *
 * Polaris is CDN-only (no npm package), and a QGIS web view reaches no
 * remote origin, so the bundle must be vendored into the plugin's `web/`
 * directory. The `polaris` entry point documents this; the elements
 * themselves only need the `<s-*>` tags to exist.
 */

import { html, nothing, type TemplateResult } from "lit";
import { ifDefined } from "lit/directives/if-defined.js";

/** Whether the Polaris `<s-*>` elements are registered on this page. */
export function polarisAvailable(): boolean {
	return (
		typeof customElements !== "undefined" &&
		customElements.get("s-button") !== undefined
	);
}

/**
 * An `<s-button>` for a run/submit action. `loading` replaces the content
 * with a spinner and disables the button, matching the native path's
 * `aria-busy` + `disabled` while pending.
 */
export function polarisButton(options: {
	readonly label: string;
	readonly disabled: boolean;
	readonly loading: boolean;
	readonly controlId: string;
	readonly onClick: (event: Event) => void;
}): TemplateResult {
	return html`<s-button
		data-part="control"
		id=${options.controlId}
		?disabled=${options.disabled || options.loading}
		?loading=${options.loading}
		@click=${options.onClick}
		>${options.label}</s-button
	>`;
}

/**
 * An `<s-text-field>` for single-line text. Polaris carries its own label
 * and error rendering, so the caller passes them through instead of
 * rendering `labelPart`/`errorPart` separately.
 */
export function polarisTextField(options: {
	readonly label: string;
	readonly value: string;
	readonly name: string;
	readonly disabled: boolean;
	readonly required: boolean;
	readonly error: string;
	readonly placeholder: string;
	readonly controlId: string;
	readonly onInput: (event: Event) => void;
}): TemplateResult {
	return html`<s-text-field
		data-part="control"
		id=${options.controlId}
		label=${options.label}
		.value=${options.value}
		name=${ifDefined(options.name === "" ? undefined : options.name)}
		?disabled=${options.disabled}
		?required=${options.required}
		error=${ifDefined(options.error === "" ? undefined : options.error)}
		placeholder=${ifDefined(
			options.placeholder === "" ? undefined : options.placeholder,
		)}
		@input=${options.onInput}
	></s-text-field>`;
}

/**
 * An `<s-select>` for a list of options. Each option is an `<s-option>`
 * child; the selected index is set as the value. Polaris fires `change`
 * with the selected value.
 */
export function polarisSelect(options: {
	readonly label: string;
	readonly options: readonly {
		readonly value: string;
		readonly label: string;
	}[];
	readonly selected: number;
	readonly name: string;
	readonly disabled: boolean;
	readonly required: boolean;
	readonly error: string;
	readonly controlId: string;
	readonly onChange: (event: Event) => void;
}): TemplateResult {
	return html`<s-select
		data-part="control"
		id=${options.controlId}
		label=${options.label}
		name=${ifDefined(options.name === "" ? undefined : options.name)}
		?disabled=${options.disabled}
		?required=${options.required}
		error=${ifDefined(options.error === "" ? undefined : options.error)}
		@change=${options.onChange}
	>
		${options.options.map(
			(option, index) =>
				html`<s-option value=${option.value} ?selected=${index === options.selected}
					>${option.label}</s-option
				>`,
		)}
	</s-select>`;
}

/**
 * An `<s-progress>` for a job's progress. `value` is 0–100; Polaris renders
 * the bar and an optional label.
 */
export function polarisProgress(options: {
	readonly label: string;
	readonly value: number;
	readonly controlId: string;
}): TemplateResult {
	return html`<s-progress
		data-part="control"
		id=${options.controlId}
		label=${options.label}
		value=${options.value}
	></s-progress>`;
}

/** Nothing, for the branches that render no Polaris component. */
export const noPolaris: typeof nothing = nothing;
