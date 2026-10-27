import { html, type PropertyDeclarations, type TemplateResult } from "lit";
import { ifDefined } from "lit/directives/if-defined.js";
import { QgisSdkElement } from "../base";
import { CONTROL_CLASSES, describedBy, errorPart, labelPart } from "../parts";

/**
 * `<qgis-distance>`: a number input with a unit, for `metres` (and any other
 * bounded numeric) fields. Reports a number, or `null` when cleared; the
 * store does the range check, the input only hints at it.
 */
export class QgisDistance extends QgisSdkElement {
	public static readonly tagName: string = "qgis-distance";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		value: { attribute: false },
		unit: { type: String },
		min: { attribute: false },
		max: { attribute: false },
		step: { attribute: false },
	};

	declare public value: number | null;
	/** The unit shown after the input. */
	declare public unit: string;
	declare public min: number | undefined;
	declare public max: number | undefined;
	declare public step: number | "any" | undefined;

	public constructor() {
		super();
		this.value = null;
		this.unit = "m";
		this.min = 0;
		this.max = undefined;
		this.step = "any";
	}

	protected override render(): TemplateResult {
		return html`${labelPart(this.controlId, this.label)}
			<span class="qs-flex qs-items-center qs-gap-1">
				<input
					data-part="control"
					class=${CONTROL_CLASSES}
					id=${this.controlId}
					name=${ifDefined(this.name === "" ? undefined : this.name)}
					type="number"
					inputmode="decimal"
					min=${ifDefined(this.min)}
					max=${ifDefined(this.max)}
					step=${ifDefined(this.step)}
					?disabled=${this.disabled}
					?required=${this.required}
					aria-required=${ifDefined(this.required ? "true" : undefined)}
					aria-invalid=${ifDefined(this.error === "" ? undefined : "true")}
					aria-describedby=${ifDefined(describedBy(this.errorId, this.error))}
					.value=${this.value === null ? "" : String(this.value)}
					@input=${this.onInput}
				/>
				<span data-part="unit" class="qs-text-muted" aria-hidden="true">${this.unit}</span>
			</span>
			${errorPart(this.errorId, this.error)}`;
	}

	private onInput(event: Event): void {
		const input = event.currentTarget as HTMLInputElement;
		// A number input sanitises what is not a number to "", so the value
		// is a number or nothing.
		const text = input.value.trim();
		const next = text === "" ? null : Number(text);
		this.value = next === null || Number.isNaN(next) ? null : next;
		this.emitChange(this.value);
	}
}
