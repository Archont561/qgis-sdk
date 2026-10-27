import { html, type PropertyDeclarations, type TemplateResult } from "lit";
import { ifDefined } from "lit/directives/if-defined.js";
import { QgisSdkElement } from "../base";
import { CONTROL_CLASSES, describedBy, errorPart, labelPart } from "../parts";

/** `AUTHORITY:CODE`, the form every `crs` field takes. */
export const AUTHID_PATTERN: RegExp = /^[A-Za-z][A-Za-z0-9_-]*:[0-9]+$/;

/** The authority ids offered before the user types; a page may pass its own. */
export const COMMON_CRS: readonly string[] = Object.freeze([
	"EPSG:4326",
	"EPSG:3857",
	"EPSG:2180",
	"EPSG:25832",
	"EPSG:25833",
	"EPSG:27700",
	"EPSG:32633",
]);

/**
 * `<qgis-crs-picker>`: a text input for an authority id with suggestions.
 * The host has no CRS search on the wire yet (`layers.get` carries a layer's
 * CRS, nothing lists them), so the picker validates the shape locally and
 * says so when the text is not `AUTHORITY:CODE`.
 */
export class QgisCrsPicker extends QgisSdkElement {
	public static readonly tagName: string = "qgis-crs-picker";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		value: { attribute: false },
		suggestions: { attribute: false },
		placeholder: { type: String },
	};

	declare public value: string | null;
	declare public suggestions: readonly string[];
	declare public placeholder: string;

	public constructor() {
		super();
		this.value = null;
		this.suggestions = COMMON_CRS;
		this.placeholder = "EPSG:4326";
	}

	/** The message shown when the current text is not an authority id. */
	public get shapeError(): string {
		const text = this.value ?? "";
		return text === "" || AUTHID_PATTERN.test(text)
			? ""
			: `Expected AUTHORITY:CODE, for example EPSG:4326, not "${text}"`;
	}

	protected override render(): TemplateResult {
		const message = this.error === "" ? this.shapeError : this.error;
		const listId = `${this.controlId}-list`;
		return html`${labelPart(this.controlId, this.label)}
			<input
				data-part="control"
				class=${CONTROL_CLASSES}
				id=${this.controlId}
				name=${ifDefined(this.name === "" ? undefined : this.name)}
				type="text"
				autocomplete="off"
				spellcheck="false"
				list=${listId}
				placeholder=${this.placeholder}
				?disabled=${this.disabled}
				?required=${this.required}
				aria-required=${ifDefined(this.required ? "true" : undefined)}
				aria-invalid=${ifDefined(message === "" ? undefined : "true")}
				aria-describedby=${ifDefined(describedBy(this.errorId, message))}
				.value=${this.value ?? ""}
				@input=${this.onInput}
			/>
			<datalist id=${listId}>
				${this.suggestions.map((authid) => html`<option value=${authid}></option>`)}
			</datalist>
			${errorPart(this.errorId, message)}`;
	}

	private onInput(event: Event): void {
		const text = (event.currentTarget as HTMLInputElement).value.trim();
		this.value = text === "" ? null : text;
		this.emitChange(this.value);
	}
}
