/**
 * What every element of the catalogue shares.
 *
 * Light DOM (decision-47 amendment): `createRenderRoot` returns the element,
 * so the page's stylesheet reaches the controls, a `<label for>` can point at
 * an input across the boundary, and a consumer's form library finds the
 * inputs. Every element carries `data-qgis-sdk="<name>"` for tests and
 * stylesheets, and marks its parts `data-part="label|control|error"`.
 */

import {
	LitElement,
	type PropertyDeclarations,
	type PropertyValues,
} from "lit";

let counter = 0;

/** The event an element raises when its value changes. */
export interface QgisChangeDetail {
	readonly name: string;
	readonly value: unknown;
}

export abstract class QgisSdkElement extends LitElement {
	public static properties: PropertyDeclarations = {
		name: { type: String, reflect: true },
		label: { type: String },
		disabled: { type: Boolean, reflect: true },
		required: { type: Boolean },
		error: { type: String },
	};

	/** The field name the element reports changes under. */
	declare public name: string;
	/** The visible label; empty renders none. */
	declare public label: string;
	declare public disabled: boolean;
	/**
	 * The Python catalogue's `required=`: an input marks its control
	 * `required`/`aria-required`; elements without a control ignore it.
	 */
	declare public required: boolean;
	/** A message to show under the control, from a form or the page. */
	declare public error: string;

	/** A document-unique id for the control, so the label can point at it. */
	protected readonly controlId: string;

	protected constructor() {
		super();
		this.name = "";
		this.label = "";
		this.disabled = false;
		this.required = false;
		this.error = "";
		counter += 1;
		this.controlId = `qgis-sdk-${counter}`;
	}

	protected override createRenderRoot(): HTMLElement | DocumentFragment {
		return this;
	}

	public override connectedCallback(): void {
		super.connectedCallback();
		this.stamp();
	}

	protected override willUpdate(changed: PropertyValues): void {
		if (changed.has("name")) {
			this.stamp();
		}
	}

	/** `data-qgis-sdk`: the field name, or the tag name when there is none. */
	private stamp(): void {
		this.dataset.qgisSdk = this.name === "" ? this.localName : this.name;
	}

	/** The id an error paragraph gets, for `aria-describedby`. */
	protected get errorId(): string {
		return `${this.controlId}-error`;
	}

	/** Raise `qgis-change` with the new value; a `qgis-form` listens. */
	protected emitChange(value: unknown): void {
		this.dispatchEvent(
			new CustomEvent<QgisChangeDetail>("qgis-change", {
				detail: { name: this.name, value },
				bubbles: true,
				composed: true,
			}),
		);
	}
}
