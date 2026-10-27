import {
	type HostQueryState,
	type HostQueryStore,
	layersQuery,
	type QgisSdkCore,
} from "@archont561/qgis-sdk";
import type { VectorLayerInfo } from "@archont561/qgis-sdk/host";
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
	BUTTON_CLASSES,
	CONTROL_CLASSES,
	describedBy,
	errorPart,
	labelPart,
	STATUS_CLASSES,
} from "../parts";

/** Any SDK built from any schema: the picker reads only `host` and `ready`. */
export type AnyQgisSdk = QgisSdkCore<unknown, unknown>;

const NONE = "";

/**
 * `<qgis-layer-picker>`: a `<select>` over the project's vector layers.
 *
 * Bound to `layersQuery`, which asks `qgis.host.granted` before any call: a
 * page without the `layers.read` grant sees the refusal and its remedy
 * instead of a `not_authorized` fault (task-70 AC #1).
 */
export class QgisLayerPicker extends QgisSdkElement {
	public static readonly tagName: string = "qgis-layer-picker";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		qgis: { attribute: false },
		value: { attribute: false },
		geometry: { type: String },
		nullable: { type: Boolean },
		placeholder: { type: String },
	};

	declare public qgis: AnyQgisSdk | null;
	/** The selected layer id. */
	declare public value: string | null;
	/** Keep only layers of this geometry type; empty keeps all. */
	declare public geometry: string;
	declare public nullable: boolean;
	declare public placeholder: string;

	private readonly layers = new StoreController<
		HostQueryState<readonly VectorLayerInfo[]>
	>(this);

	public constructor() {
		super();
		this.qgis = null;
		this.value = null;
		this.geometry = "";
		this.nullable = false;
		this.placeholder = "Choose a layer…";
	}

	/** The query behind the select, for a page that wants its state. */
	public get query(): HostQueryStore<readonly VectorLayerInfo[]> | null {
		return this.layers.store as HostQueryStore<
			readonly VectorLayerInfo[]
		> | null;
	}

	/** The layers currently offered. */
	public get options(): readonly VectorLayerInfo[] {
		const state = this.layers.value;
		if (state === undefined || state.status !== "ok") {
			return [];
		}
		return this.geometry === ""
			? state.value
			: state.value.filter((layer) => layer.geometry_type === this.geometry);
	}

	/** The selected layer, when the list has it. */
	public get selected(): VectorLayerInfo | null {
		return this.options.find((layer) => layer.id === this.value) ?? null;
	}

	/** Ask the host again. */
	public refresh(): Promise<readonly VectorLayerInfo[] | undefined> {
		return this.query?.refresh() ?? Promise.resolve(undefined);
	}

	protected override willUpdate(changed: PropertyValues): void {
		super.willUpdate(changed);
		if (changed.has("qgis")) {
			this.query?.abort();
			this.layers.store = this.qgis === null ? null : layersQuery(this.qgis);
			void this.refresh();
		}
	}

	protected override render(): TemplateResult {
		const state = this.layers.value ?? { status: "idle" as const };
		const refused = state.status === "refused";
		const message =
			this.error !== ""
				? this.error
				: refused
					? `${state.message}; add "layers.read" to the view's grants`
					: state.status === "error"
						? state.error.message
						: "";
		const options = this.options;
		const known = options.some((layer) => layer.id === this.value);
		return html`${labelPart(this.controlId, this.label)}
			<span class="qs-flex qs-items-center qs-gap-1">
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
							? html`<option value=${NONE} ?selected=${!known}>${this.placeholder}</option>`
							: nothing
					}
					${options.map(
						(layer) =>
							html`<option value=${layer.id} ?selected=${layer.id === this.value}>${layer.name}</option>`,
					)}
				</select>
				${
					refused
						? nothing
						: html`<button data-part="refresh" class=${BUTTON_CLASSES} type="button" ?disabled=${this.disabled || this.qgis === null} @click=${this.refresh}>Refresh</button>`
				}
			</span>
			${
				state.status === "loading"
					? html`<p data-part="status" class=${STATUS_CLASSES} role="status">Loading layers…</p>`
					: nothing
			}
			${errorPart(this.errorId, message)}`;
	}

	private onChange(event: Event): void {
		const select = event.currentTarget as HTMLSelectElement;
		this.value = select.value === NONE ? null : select.value;
		this.emitChange(this.value);
	}
}
