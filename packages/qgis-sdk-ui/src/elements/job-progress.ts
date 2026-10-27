import type { Store } from "@archont561/qgis-sdk";
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
import { BUTTON_CLASSES, STATUS_CLASSES } from "../parts";

/** Where a job stands, as the element shows it. */
export type ProgressStatus = "idle" | "pending" | "ok" | "error";

/** What the element shows: a status, an optional fraction, a message. */
export interface Progress {
	readonly status: ProgressStatus;
	/** `0..1` when known; `null` or absent renders an indeterminate bar. */
	readonly fraction?: number | null;
	readonly message?: string;
}

/** How a store snapshot becomes a {@link Progress}. */
export type ProgressReader<T> = (snapshot: T) => Progress;

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

/**
 * The default reader: an `OperationState`, a `FormState` (through its
 * `submission`), a `StreamState`, or anything shaped like a `Progress`.
 */
export function readProgress(snapshot: unknown): Progress {
	if (!isRecord(snapshot)) {
		return { status: "idle" };
	}
	if (isRecord(snapshot.submission)) {
		return readProgress(snapshot.submission);
	}
	const status = snapshot.status;
	const fraction =
		typeof snapshot.fraction === "number" ? snapshot.fraction : null;
	const message =
		typeof snapshot.message === "string"
			? snapshot.message
			: snapshot.error instanceof Error
				? snapshot.error.message
				: undefined;
	switch (status) {
		case "pending":
		case "opening":
		case "open":
			return {
				status: "pending",
				fraction,
				...(message === undefined ? {} : { message }),
			};
		case "ok":
		case "ended":
			return {
				status: "ok",
				fraction: 1,
				...(message === undefined ? {} : { message }),
			};
		case "error":
		case "failed":
			return {
				status: "error",
				fraction,
				...(message === undefined ? {} : { message }),
			};
		default:
			return {
				status: "idle",
				fraction,
				...(message === undefined ? {} : { message }),
			};
	}
}

const STATUS_TEXT: Readonly<Record<ProgressStatus, string>> = Object.freeze({
	idle: "",
	pending: "Running…",
	ok: "Done",
	error: "Failed",
});

/**
 * `<qgis-job-progress>`: a progress bar with a message and an optional
 * cancel button.
 *
 * Driven either by the `status`/`fraction`/`message` properties or by any
 * store through a reader. A `JobHandle` crosses the wire as `{id, status}`
 * today; a progress stream from the host is future work (task-70 notes), so
 * a page that has one feeds it through `read`.
 */
export class QgisJobProgress extends QgisSdkElement {
	public static readonly tagName: string = "qgis-job-progress";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		status: { type: String },
		fraction: { attribute: false },
		message: { type: String },
		store: { attribute: false },
		read: { attribute: false },
		cancel: { attribute: false },
	};

	declare public status: ProgressStatus;
	declare public fraction: number | null;
	declare public message: string;
	/** A store to follow; its snapshots go through `read`. */
	declare public store: Store<unknown> | null;
	declare public read: ProgressReader<unknown>;
	/** Shown as a button while pending; `null` shows none. */
	declare public cancel: (() => void) | null;

	private readonly source = new StoreController<unknown>(this);

	public constructor() {
		super();
		this.status = "idle";
		this.fraction = null;
		this.message = "";
		this.store = null;
		this.read = readProgress;
		this.cancel = null;
	}

	/** What is shown now: the store's reading when there is one, else the properties. */
	public get progress(): Progress {
		if (this.source.store !== null && this.source.value !== undefined) {
			return this.read(this.source.value);
		}
		return {
			status: this.status,
			fraction: this.fraction,
			message: this.message,
		};
	}

	protected override willUpdate(changed: PropertyValues): void {
		super.willUpdate(changed);
		if (changed.has("store")) {
			this.source.store = this.store;
		}
	}

	protected override render(): TemplateResult {
		const { status, fraction, message } = this.progress;
		const known = typeof fraction === "number" && Number.isFinite(fraction);
		const value = known ? Math.min(1, Math.max(0, fraction)) : undefined;
		const text =
			message === undefined || message === "" ? STATUS_TEXT[status] : message;
		return html`${
			this.label === ""
				? nothing
				: html`<span data-part="label" class="qs-block qs-text-fg qs-mb-1" id=${`${this.controlId}-label`}>${this.label}</span>`
		}
			<span class="qs-flex qs-items-center qs-gap-2">
				<progress
					data-part="control"
					data-status=${status}
					class="qs-flex-1 qs-h-2 qs-accent-accent"
					id=${this.controlId}
					aria-labelledby=${ifDefined(this.label === "" ? undefined : `${this.controlId}-label`)}
					aria-busy=${ifDefined(status === "pending" ? "true" : undefined)}
					max="1"
					value=${ifDefined(status === "idle" ? 0 : value)}
				></progress>
				${
					this.cancel !== null && status === "pending"
						? html`<button data-part="cancel" class=${BUTTON_CLASSES} type="button" @click=${this.onCancel}>Cancel</button>`
						: nothing
				}
			</span>
			<output
				data-part=${status === "error" ? "error" : "status"}
				class=${status === "error" ? "qs-block qs-mt-1 qs-text-danger" : STATUS_CLASSES}
				for=${this.controlId}
				role="status"
				aria-live="polite"
			>${text}</output>`;
	}

	private onCancel(): void {
		this.dispatchEvent(
			new CustomEvent("qgis-cancel", { bubbles: true, composed: true }),
		);
		this.cancel?.();
	}
}
