import {
	type HostQueryState,
	type HostQueryStore,
	layerFieldsQuery,
} from "@archont561/qgis-sdk";
import {
	html,
	nothing,
	type PropertyDeclarations,
	type PropertyValues,
	type TemplateResult,
} from "lit";
import { ifDefined } from "lit/directives/if-defined.js";
import { QgisSdkElement } from "../base";
import { StoreController } from "../controller";
import {
	CONTROL_CLASSES,
	describedBy,
	errorPart,
	labelPart,
	STATUS_CLASSES,
} from "../parts";
import type { AnyQgisSdk } from "./layer-picker";

const NONE = "";

/**
 * `<qgis-field-picker>`: a `<select>` over the fields of one layer, for a
 * `field` input whose `of` names a layer input. Bound to `layerFieldsQuery`,
 * so the `layers.read` grant is checked before any call; without a layer it
 * waits, saying so.
 */
/** What `of` needs of a layer picker: its value and its change event. */
export interface LayerPickerLike extends EventTarget {
	readonly value: string | null;
}

export class QgisFieldPicker extends QgisSdkElement {
	public static readonly tagName: string = "qgis-field-picker";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		qgis: { attribute: false },
		layer: { attribute: false },
		value: { attribute: false },
		nullable: { type: Boolean },
		placeholder: { type: String },
	};

	declare public qgis: AnyQgisSdk | null;
	/** The id of the layer whose fields are offered. */
	declare public layer: string | null;
	declare public value: string | null;
	declare public nullable: boolean;
	declare public placeholder: string;

	private readonly fields = new StoreController<
		HostQueryState<readonly string[]>
	>(this);

	public constructor() {
		super();
		this.qgis = null;
		this.layer = null;
		this.value = null;
		this.nullable = false;
		this.placeholder = "Choose a field…";
	}

	public get query(): HostQueryStore<readonly string[]> | null {
		return this.fields.store as HostQueryStore<readonly string[]> | null;
	}

	/** The field names currently offered. */
	public get options(): readonly string[] {
		const state = this.fields.value;
		return state !== undefined && state.status === "ok" ? state.value : [];
	}

	public refresh(): Promise<readonly string[] | undefined> {
		return this.query?.refresh() ?? Promise.resolve(undefined);
	}

	/**
	 * The Python `FieldPicker(of=)`: a `<qgis-layer-picker>` to follow. Its
	 * current value becomes `layer` at once and on every `qgis-change` it
	 * raises; `null` stops following and keeps the last layer.
	 */
	public get of(): LayerPickerLike | null {
		return this.followed;
	}

	public set of(picker: LayerPickerLike | null) {
		this.follow(picker);
	}

	public override disconnectedCallback(): void {
		super.disconnectedCallback();
		this.follow(null);
	}

	protected override willUpdate(changed: PropertyValues): void {
		super.willUpdate(changed);
		if (changed.has("qgis") || changed.has("layer")) {
			this.query?.abort();
			this.fields.store =
				this.qgis === null || this.layer === null
					? null
					: layerFieldsQuery(this.qgis, this.layer);
			void this.refresh();
		}
	}

	protected override render(): TemplateResult {
		const state = this.fields.value ?? { status: "idle" as const };
		const message =
			this.error !== ""
				? this.error
				: state.status === "refused"
					? `${state.message}; add "layers.read" to the view's grants`
					: state.status === "error"
						? state.error.message
						: "";
		const options = this.options;
		const known = this.value !== null && options.includes(this.value);
		const waiting = this.layer === null || this.qgis === null;
		return html`${labelPart(this.controlId, this.label)}
			<select
				data-part="control"
				class=${CONTROL_CLASSES}
				id=${this.controlId}
				name=${ifDefined(this.name === "" ? undefined : this.name)}
				?disabled=${this.disabled || state.status !== "ok"}
				?required=${this.required}
				aria-required=${ifDefined(this.required ? "true" : undefined)}
				aria-busy=${ifDefined(state.status === "loading" ? "true" : undefined)}
				aria-invalid=${ifDefined(message === "" ? undefined : "true")}
				aria-describedby=${ifDefined(describedBy(this.errorId, message))}
				.value=${known ? (this.value as string) : NONE}
				@change=${this.onChange}
			>
				${
					this.nullable || !known
						? html`<option value=${NONE} ?selected=${!known}>${waiting ? "Choose a layer first" : this.placeholder}</option>`
						: nothing
				}
				${options.map(
					(field) =>
						html`<option value=${field} ?selected=${field === this.value}>${field}</option>`,
				)}
			</select>
			${
				state.status === "loading"
					? html`<p data-part="status" class=${STATUS_CLASSES} role="status">Loading fields…</p>`
					: nothing
			}
			${errorPart(this.errorId, message)}`;
	}

	private followed: LayerPickerLike | null = null;
	private readonly onLayerChange = (): void => {
		if (this.followed !== null) {
			this.layer = this.followed.value;
		}
	};

	private follow(picker: LayerPickerLike | null): void {
		if (this.followed === picker) {
			return;
		}
		this.followed?.removeEventListener("qgis-change", this.onLayerChange);
		this.followed = picker;
		if (picker !== null) {
			picker.addEventListener("qgis-change", this.onLayerChange);
			this.layer = picker.value;
		}
	}

	private onChange(event: Event): void {
		const select = event.currentTarget as HTMLSelectElement;
		this.value = select.value === NONE ? null : select.value;
		this.emitChange(this.value);
	}
}
