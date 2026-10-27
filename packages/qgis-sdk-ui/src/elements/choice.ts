import { html, type PropertyDeclarations, type TemplateResult } from "lit";
import { ifDefined } from "lit/directives/if-defined.js";
import { QgisSdkElement } from "../base";
import { CONTROL_CLASSES, describedBy, errorPart, labelPart } from "../parts";

/** One option of a choice: a bare value, or a value with its own label. */
export type Choice =
	| string
	| number
	| boolean
	| { readonly value: unknown; readonly label: string };

const EMPTY = "";

function choiceValue(choice: Choice): unknown {
	return typeof choice === "object" ? choice.value : choice;
}

function labelOf(choice: Choice): string {
	return typeof choice === "object" ? choice.label : String(choice);
}

/**
 * `<qgis-choice>`: a `<select>` over declared choices (a `choice` field's
 * `enum`). Options are addressed by index, so a numeric or boolean choice
 * comes back with its own type, not as a string.
 */
export class QgisChoice extends QgisSdkElement {
	public static readonly tagName: string = "qgis-choice";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		options: { attribute: false },
		value: { attribute: false },
		nullable: { type: Boolean },
		placeholder: { type: String },
	};

	/** The options offered, as the Python `Choice(options=)`. */
	declare public options: readonly Choice[];
	declare public value: unknown;
	/** Offer an empty option that reports `null`. */
	declare public nullable: boolean;
	declare public placeholder: string;

	public constructor() {
		super();
		this.options = [];
		this.value = null;
		this.nullable = false;
		this.placeholder = "Choose…";
	}

	/** The same list under its first name; `options` is the shared spelling. */
	public get choices(): readonly Choice[] {
		return this.options;
	}

	public set choices(value: readonly Choice[]) {
		this.options = value;
	}

	protected override render(): TemplateResult {
		const selected = this.options.findIndex((choice) =>
			Object.is(choiceValue(choice), this.value),
		);
		return html`${labelPart(this.controlId, this.label)}
			<select
				data-part="control"
				class=${CONTROL_CLASSES}
				id=${this.controlId}
				name=${ifDefined(this.name === "" ? undefined : this.name)}
				?disabled=${this.disabled}
				?required=${this.required}
				aria-required=${ifDefined(this.required ? "true" : undefined)}
				aria-invalid=${ifDefined(this.error === "" ? undefined : "true")}
				aria-describedby=${ifDefined(describedBy(this.errorId, this.error))}
				.value=${selected < 0 ? EMPTY : String(selected)}
				@change=${this.onChange}
			>
				${
					this.nullable || selected < 0
						? html`<option value=${EMPTY} ?selected=${selected < 0}>${this.placeholder}</option>`
						: null
				}
				${this.options.map(
					(choice, index) =>
						html`<option value=${String(index)} ?selected=${index === selected}>${labelOf(choice)}</option>`,
				)}
			</select>
			${errorPart(this.errorId, this.error)}`;
	}

	private onChange(event: Event): void {
		const select = event.currentTarget as HTMLSelectElement;
		const next =
			select.value === EMPTY
				? null
				: choiceValue(this.options[Number(select.value)] as Choice);
		this.value = next;
		this.emitChange(next);
	}
}
