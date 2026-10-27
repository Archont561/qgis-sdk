import type { FormField, FormState } from "@archont561/qgis-sdk";
import {
	html,
	nothing,
	type PropertyDeclarations,
	type PropertyValues,
	type TemplateResult,
} from "lit";
import { ifDefined } from "lit/directives/if-defined.js";
import { type QgisChangeDetail, QgisSdkElement } from "../base";
import { StoreController } from "../controller";
import { CONTROL_CLASSES, describedBy, errorPart, labelPart } from "../parts";
import type { FileRefPicker } from "./file-input";
import type { AnyQgisSdk } from "./layer-picker";
import type { AnyFormStore } from "./run-button";

/** Where a `file`/`directory` field of the form gets a reference from. */
export type Pickers = Readonly<Record<string, FileRefPicker>>;

const NUMBER_INPUT: ReadonlySet<string> = new Set([
	"integer",
	"number",
	"range",
]);

function detail<T>(field: FormField, key: string): T | undefined {
	return field.details[key] as T | undefined;
}

/**
 * `<qgis-form>`: one control per declared field of a `FormStore`, in
 * declaration order, with the run button and the submission's outcome.
 *
 * The form composes by properties (decision-55): it renders the catalogue's
 * elements for the kinds that have one and plain inputs for the rest,
 * listens to their `qgis-change`, and writes into the store. Errors appear
 * once `submit` was attempted, next to the field they name.
 */
export class QgisForm extends QgisSdkElement {
	public static readonly tagName: string = "qgis-form";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		store: { attribute: false },
		qgis: { attribute: false },
		pickers: { attribute: false },
		submitLabel: { type: String, attribute: "submit-label" },
	};

	declare public store: AnyFormStore | null;
	/** The SDK the pickers read the host through. */
	declare public qgis: AnyQgisSdk | null;
	declare public pickers: Pickers;
	declare public submitLabel: string;

	private readonly form = new StoreController<FormState<unknown>>(this);

	public constructor() {
		super();
		this.store = null;
		this.qgis = null;
		this.pickers = {};
		this.submitLabel = "";
	}

	/** The store's current state, when there is one. */
	public get state(): FormState<unknown> | undefined {
		return this.form.value;
	}

	protected override willUpdate(changed: PropertyValues): void {
		super.willUpdate(changed);
		if (changed.has("store")) {
			this.form.store = this.store;
		}
	}

	protected override render(): TemplateResult {
		const store = this.store;
		const state = this.form.value;
		if (store === null || state === undefined) {
			return html`<p data-part="status" role="status">No form bound.</p>`;
		}
		const submission = state.submission;
		const failure =
			this.error !== ""
				? this.error
				: submission.status === "error"
					? submission.error.message
					: "";
		return html`<form
			data-part="control"
			class="qs-m-0"
			id=${this.controlId}
			novalidate
			aria-labelledby=${ifDefined(this.label === "" ? undefined : `${this.controlId}-label`)}
			@qgis-change=${this.onFieldChange}
			@submit=${this.onSubmit}
		>
			${
				this.label === ""
					? nothing
					: html`<h2 data-part="label" class="qs-m-0 qs-mb-2 qs-text-fg qs-text-base" id=${`${this.controlId}-label`}>${this.label}</h2>`
			}
			${store.fields.map((field) => this.renderField(field, state))}
			<div class="qs-flex qs-items-center qs-gap-2 qs-mt-2">
				<qgis-run-button
					.form=${store}
					.label=${this.submitLabel === "" ? store.title : this.submitLabel}
					?disabled=${this.disabled}
				></qgis-run-button>
				${
					submission.status === "pending"
						? html`<span data-part="status" class="qs-text-muted" role="status">Running…</span>`
						: nothing
				}
			</div>
			${errorPart(this.errorId, failure)}
		</form>`;
	}

	private renderField(
		field: FormField,
		state: FormState<unknown>,
	): TemplateResult {
		const value = state.values[field.name];
		const error = state.submitted ? (state.errors[field.name] ?? "") : "";
		const common = {
			name: field.name,
			label: field.label,
			error,
			disabled: this.disabled,
		};
		let control: TemplateResult;
		switch (field.kind) {
			case "layer":
				control = html`<qgis-layer-picker
					.name=${common.name} .label=${common.label} .error=${common.error} ?disabled=${common.disabled}
					.qgis=${this.qgis}
					.value=${typeof value === "string" ? value : null}
					.nullable=${!field.required || field.nullable}
				></qgis-layer-picker>`;
				break;
			case "field":
				control = html`<qgis-field-picker
					.name=${common.name} .label=${common.label} .error=${common.error} ?disabled=${common.disabled}
					.qgis=${this.qgis}
					.layer=${this.layerFor(field, state)}
					.value=${typeof value === "string" ? value : null}
					.nullable=${!field.required || field.nullable}
				></qgis-field-picker>`;
				break;
			case "crs":
				control = html`<qgis-crs-picker
					.name=${common.name} .label=${common.label} .error=${common.error} ?disabled=${common.disabled}
					.value=${typeof value === "string" ? value : null}
				></qgis-crs-picker>`;
				break;
			case "choice":
				control = html`<qgis-choice
					.name=${common.name} .label=${common.label} .error=${common.error} ?disabled=${common.disabled}
					.options=${field.choices as readonly string[]}
					.value=${value ?? null}
					.nullable=${!field.required || field.nullable}
				></qgis-choice>`;
				break;
			case "metres":
				control = html`<qgis-distance
					.name=${common.name} .label=${common.label} .error=${common.error} ?disabled=${common.disabled}
					.value=${typeof value === "number" ? value : null}
					.min=${detail<number>(field, "minimum") ?? 0}
					.max=${detail<number>(field, "maximum")}
					.step=${detail<number>(field, "step") ?? "any"}
				></qgis-distance>`;
				break;
			case "file":
				control = html`<qgis-file-input
					.name=${common.name} .label=${common.label} .error=${common.error} ?disabled=${common.disabled}
					.value=${value ?? null}
					.pick=${this.pickers[field.name] ?? null}
					.filters=${detail<readonly string[]>(field, "filters") ?? []}
				></qgis-file-input>`;
				break;
			case "directory":
				control = html`<qgis-directory-input
					.name=${common.name} .label=${common.label} .error=${common.error} ?disabled=${common.disabled}
					.value=${value ?? null}
					.pick=${this.pickers[field.name] ?? null}
				></qgis-directory-input>`;
				break;
			default:
				control = this.renderPlain(field, value, error);
		}
		return html`<div data-field=${field.name} class="qs-mb-3">${control}</div>`;
	}

	/** A plain `<input>` for the kinds without an element of their own. */
	private renderPlain(
		field: FormField,
		value: unknown,
		error: string,
	): TemplateResult {
		const id = `${this.controlId}-${field.name}`;
		const errorId = `${id}-error`;
		if (field.kind === "boolean") {
			return html`<label data-part="label" class="qs-inline-flex qs-items-center qs-gap-2 qs-text-fg" for=${id}>
					<input
						data-part="control"
						class="qs-accent-accent"
						id=${id}
						name=${field.name}
						type="checkbox"
						?disabled=${this.disabled}
						.checked=${value === true}
						aria-invalid=${ifDefined(error === "" ? undefined : "true")}
						aria-describedby=${ifDefined(describedBy(errorId, error))}
						@change=${(event: Event) =>
							this.set(
								field.name,
								(event.currentTarget as HTMLInputElement).checked,
							)}
					/>${field.label}</label>
				${errorPart(errorId, error)}`;
		}
		const type =
			field.kind === "colour"
				? "color"
				: NUMBER_INPUT.has(field.kind)
					? "number"
					: "text";
		return html`${labelPart(id, field.label)}
			<input
				data-part="control"
				class=${CONTROL_CLASSES}
				id=${id}
				name=${field.name}
				type=${type}
				min=${ifDefined(detail<number>(field, "minimum"))}
				max=${ifDefined(detail<number>(field, "maximum"))}
				step=${ifDefined(
					type === "number"
						? (detail<number>(field, "step") ??
								(field.kind === "integer" ? 1 : "any"))
						: undefined,
				)}
				?required=${field.required}
				?disabled=${this.disabled}
				aria-invalid=${ifDefined(error === "" ? undefined : "true")}
				aria-describedby=${ifDefined(describedBy(errorId, error))}
				.value=${value === undefined || value === null ? "" : String(value)}
				@input=${(event: Event) => {
					const text = (event.currentTarget as HTMLInputElement).value;
					this.set(field.name, text === "" && field.nullable ? null : text);
				}}
			/>
			${errorPart(errorId, error)}`;
	}

	/** The layer id a `field` input's `of` currently names. */
	private layerFor(field: FormField, state: FormState<unknown>): string | null {
		const of = detail<string>(field, "of");
		if (of === undefined) {
			return null;
		}
		const layer = state.values[of];
		return typeof layer === "string" && layer !== "" ? layer : null;
	}

	private set(name: string, value: unknown): void {
		this.store?.set(name, value);
	}

	private onFieldChange(event: Event): void {
		const { name, value } = (event as CustomEvent<QgisChangeDetail>).detail;
		if (name !== "") {
			event.stopPropagation();
			this.set(name, value);
		}
	}

	private onSubmit(event: Event): void {
		event.preventDefault();
		void this.store?.submit();
	}
}
