import type { FormStore, OperationStore, Store } from "@archont561/qgis-sdk";
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
import { BUTTON_CLASSES } from "../parts";
import { readProgress } from "./job-progress";

/** Any form store: the button only submits and reads its submission. */
export type AnyFormStore = FormStore<object, unknown>;
/** Any operation store: the button only runs it with `input`. */
export type AnyOperationStore = OperationStore<unknown, unknown>;

/**
 * `<qgis-run-button>`: submits a form store or runs an operation store,
 * and shows where the call stands.
 *
 * Disabled and `aria-busy` while pending; raises `qgis-result` with the
 * value when the call succeeds. A page with neither store gets a plain
 * button that raises `qgis-run` and nothing else.
 */
export class QgisRunButton extends QgisSdkElement {
	public static readonly tagName: string = "qgis-run-button";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		form: { attribute: false },
		operation: { attribute: false },
		input: { attribute: false },
		pendingLabel: { type: String, attribute: "pending-label" },
		text: { type: String },
	};

	declare public form: AnyFormStore | null;
	declare public operation: AnyOperationStore | null;
	/** The input `operation.run` is called with. */
	declare public input: unknown;
	declare public pendingLabel: string;

	private readonly state = new StoreController<unknown>(this);

	public constructor() {
		super();
		this.form = null;
		this.operation = null;
		this.input = undefined;
		this.pendingLabel = "";
	}

	/** The Python `Button(text=)`: the caption, the same property as `label`. */
	public get text(): string {
		return this.label;
	}

	public set text(value: string) {
		this.label = value;
	}

	/** The call is in flight. */
	public get pending(): boolean {
		const snapshot = this.state.value;
		return (
			snapshot !== undefined && readProgress(snapshot).status === "pending"
		);
	}

	/** Submit or run, as a click would. */
	public async run(): Promise<unknown> {
		this.dispatchEvent(
			new CustomEvent("qgis-run", { bubbles: true, composed: true }),
		);
		const result =
			this.form !== null
				? await this.form.submit()
				: this.operation !== null
					? await this.operation.run(this.input)
					: undefined;
		if (result !== undefined) {
			this.dispatchEvent(
				new CustomEvent("qgis-result", {
					detail: result,
					bubbles: true,
					composed: true,
				}),
			);
		}
		return result;
	}

	protected override willUpdate(changed: PropertyValues): void {
		super.willUpdate(changed);
		if (changed.has("form") || changed.has("operation")) {
			this.state.store = (this.form ?? this.operation) as Store<unknown> | null;
		}
	}

	protected override render(): TemplateResult {
		const pending = this.pending;
		const text = this.label === "" ? "Run" : this.label;
		return html`<button
				data-part="control"
				class=${`${BUTTON_CLASSES} qs-bg-accent qs-text-accent-fg qs-border-accent`}
				id=${this.controlId}
				type=${this.form === null ? "button" : "submit"}
				?disabled=${this.disabled || pending}
				aria-busy=${ifDefined(pending ? "true" : undefined)}
				@click=${this.onClick}
			>${pending && this.pendingLabel !== "" ? this.pendingLabel : text}</button>
			${
				this.error === ""
					? nothing
					: html`<p data-part="error" class="qs-m-0 qs-mt-1 qs-text-danger" id=${this.errorId} role="alert">${this.error}</p>`
			}`;
	}

	private onClick(event: Event): void {
		// A form store submits through the store, not the browser.
		event.preventDefault();
		void this.run();
	}
}
