import type { FileRef } from "@archont561/qgis-sdk/host";
import { html, type PropertyDeclarations, type TemplateResult } from "lit";
import { ifDefined } from "lit/directives/if-defined.js";
import { QgisSdkElement } from "../base";
import {
	BUTTON_CLASSES,
	CONTROL_CLASSES,
	describedBy,
	errorPart,
	labelPart,
} from "../parts";
import { polarisAvailable, polarisButton, polarisTextField } from "../polaris";

/** How a page obtains a reference: a host dialog, a drop, a fixture. */
export type FileRefPicker = () => Promise<FileRef | null | undefined>;

/**
 * `<qgis-file-input>`: shows the `FileRef` a `file` field holds and lets the
 * user replace or clear it.
 *
 * A page never types a path (decision-20): a reference is minted by the host
 * and handed to the page. The wire has no `files.pick` operation yet, so the
 * element takes a `pick` callback - the page decides where a reference
 * comes from - and disables the button, saying why, when there is none.
 */
export class QgisFileInput extends QgisSdkElement {
	public static readonly tagName: string = "qgis-file-input";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		value: { attribute: false },
		pick: { attribute: false },
		filters: { attribute: false },
		placeholder: { type: String },
	};

	declare public value: FileRef | null;
	declare public pick: FileRefPicker | null;
	/** The declared filters, shown as a hint; the host applies them. */
	declare public filters: readonly string[];
	declare public placeholder: string;

	/** What this element picks; the subclass says `directory`. */
	protected get kind(): FileRef["kind"] {
		return "file";
	}

	public constructor() {
		super();
		this.value = null;
		this.pick = null;
		this.filters = [];
		this.placeholder = "No file chosen";
	}

	protected override render(): TemplateResult {
		const noun = this.kind === "directory" ? "directory" : "file";
		const hint =
			this.pick === null
				? `This page has no ${noun} picker; the host hands references in.`
				: this.filters.length === 0
					? undefined
					: this.filters.join(", ");
		const shown = this.value === null ? "" : (this.value.name ?? this.value.id);
		if (polarisAvailable()) {
			return html`${polarisTextField({
				label: this.label,
				value: shown,
				name: this.name,
				disabled: this.disabled,
				required: this.required,
				error: this.error,
				placeholder: this.placeholder,
				controlId: this.controlId,
				onInput: () => {},
			})}
				${polarisButton({
					label: "Choose…",
					disabled: this.disabled || this.pick === null,
					loading: false,
					controlId: `${this.controlId}-pick`,
					onClick: this.onPick,
				})}
				${polarisButton({
					label: "Clear",
					disabled: this.disabled || this.value === null,
					loading: false,
					controlId: `${this.controlId}-clear`,
					onClick: this.onClear,
				})}`;
		}
		return html`${labelPart(this.controlId, this.label)}
			<span class="qs-flex qs-items-center qs-gap-1">
				<input
					data-part="control"
					class=${CONTROL_CLASSES}
					id=${this.controlId}
					name=${ifDefined(this.name === "" ? undefined : this.name)}
					type="text"
					readonly
					placeholder=${this.placeholder}
					?disabled=${this.disabled}
					?required=${this.required}
					aria-required=${ifDefined(this.required ? "true" : undefined)}
					aria-invalid=${ifDefined(this.error === "" ? undefined : "true")}
					aria-describedby=${ifDefined(describedBy(this.errorId, this.error))}
					.value=${shown}
				/>
				<button
					data-part="pick"
					class=${BUTTON_CLASSES}
					type="button"
					title=${ifDefined(hint)}
					?disabled=${this.disabled || this.pick === null}
					@click=${this.onPick}
				>Choose…</button>
				<button
					data-part="clear"
					class=${BUTTON_CLASSES}
					type="button"
					?disabled=${this.disabled || this.value === null}
					@click=${this.onClear}
				>Clear</button>
			</span>
			${errorPart(this.errorId, this.error)}`;
	}

	private async onPick(): Promise<void> {
		if (this.pick === null) {
			return;
		}
		const picked = await this.pick();
		if (picked === null || picked === undefined) {
			return;
		}
		if (picked.kind !== this.kind) {
			this.error = `Expected a ${this.kind}, the picker returned a ${picked.kind}`;
			return;
		}
		this.error = "";
		this.value = picked;
		this.emitChange(picked);
	}

	private onClear(): void {
		this.value = null;
		this.emitChange(null);
	}
}

/** `<qgis-directory-input>`: the same control for a `directory` field. */
export class QgisDirectoryInput extends QgisFileInput {
	public static override readonly tagName: string = "qgis-directory-input";

	public constructor() {
		super();
		this.placeholder = "No directory chosen";
	}

	protected override get kind(): FileRef["kind"] {
		return "directory";
	}
}
