import type { Store } from "@archont561/qgis-sdk";
import {
	html,
	nothing,
	type PropertyDeclarations,
	type PropertyValues,
	type TemplateResult,
} from "lit";
import { QgisSdkElement } from "../base";
import { StoreController } from "../controller";
import { BUTTON_CLASSES } from "../parts";

/** How a store snapshot becomes lines. */
export type LinesReader<T> = (snapshot: T) => readonly string[];

/**
 * The default reader: an array of strings, anything with a `lines` array,
 * or a `StreamState` whose `lastEvent` is a string or has a `message`.
 */
export function readLines(snapshot: unknown): readonly string[] {
	if (Array.isArray(snapshot)) {
		return snapshot.map(String);
	}
	if (typeof snapshot !== "object" || snapshot === null) {
		return [];
	}
	const record = snapshot as Record<string, unknown>;
	if (Array.isArray(record.lines)) {
		return record.lines.map(String);
	}
	const event = record.lastEvent;
	if (typeof event === "string") {
		return [event];
	}
	if (
		typeof event === "object" &&
		event !== null &&
		typeof (event as Record<string, unknown>).message === "string"
	) {
		return [(event as Record<string, string>).message];
	}
	return [];
}

/**
 * `<qgis-log-view>`: a scrolling, screen-reader-announced log.
 *
 * Lines come from the `lines` property, from `append`, or from a store
 * through `read`; a store's reading is appended on every change, so a
 * stream of events accumulates. `limit` keeps the newest lines.
 */
export class QgisLogView extends QgisSdkElement {
	public static readonly tagName: string = "qgis-log-view";
	public static override properties: PropertyDeclarations = {
		...QgisSdkElement.properties,
		lines: { attribute: false },
		limit: { type: Number },
		store: { attribute: false },
		read: { attribute: false },
		clearable: { type: Boolean },
	};

	declare public lines: readonly string[];
	declare public limit: number;
	declare public store: Store<unknown> | null;
	declare public read: LinesReader<unknown>;
	/** Offer a "Clear" button. */
	declare public clearable: boolean;

	private readonly source = new StoreController<unknown>(this);
	private lastSnapshot: unknown = undefined;

	public constructor() {
		super();
		this.lines = [];
		this.limit = 500;
		this.store = null;
		this.read = readLines;
		this.clearable = false;
	}

	/** Add lines at the end, dropping the oldest beyond `limit`. */
	public append(...lines: readonly string[]): void {
		const next = [...this.lines, ...lines];
		this.lines = Object.freeze(
			next.length > this.limit ? next.slice(next.length - this.limit) : next,
		);
	}

	public clear(): void {
		this.lines = Object.freeze([]);
	}

	protected override willUpdate(changed: PropertyValues): void {
		super.willUpdate(changed);
		if (changed.has("store")) {
			this.source.store = this.store;
			this.lastSnapshot = undefined;
		}
		const snapshot = this.source.value;
		if (
			this.source.store !== null &&
			snapshot !== undefined &&
			!Object.is(snapshot, this.lastSnapshot)
		) {
			this.lastSnapshot = snapshot;
			this.append(...this.read(snapshot));
		}
	}

	protected override updated(): void {
		const pre = this.querySelector<HTMLElement>("[data-part='control']");
		if (pre !== null) {
			pre.scrollTop = pre.scrollHeight;
		}
	}

	protected override render(): TemplateResult {
		return html`${
			this.label === ""
				? nothing
				: html`<span data-part="label" class="qs-block qs-text-fg qs-mb-1" id=${`${this.controlId}-label`}>${this.label}</span>`
		}
			<pre
				data-part="control"
				class="qs-m-0 qs-max-h-60 qs-overflow-auto qs-rounded qs-border qs-border-border qs-bg-surface qs-text-surface-fg qs-p-2 qs-font-mono qs-text-xs qs-whitespace-pre-wrap"
				id=${this.controlId}
				role="log"
				aria-live="polite"
				aria-labelledby=${this.label === "" ? nothing : `${this.controlId}-label`}
				tabindex="0"
			>${this.lines.join("\n")}</pre>
			${
				this.clearable
					? html`<button data-part="clear" class=${`${BUTTON_CLASSES} qs-mt-1`} type="button" ?disabled=${this.lines.length === 0} @click=${this.clear}>Clear</button>`
					: nothing
			}`;
	}
}
